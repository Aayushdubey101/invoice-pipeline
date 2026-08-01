"""
Pipeline orchestrator. Chains all stages.
Invariant: stages NEVER raise — errors attach to document.errors[].
"""

import time

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.confidence.engine import ConfidenceEngine
from invoice_pipeline.db.models import LEGACY_WORKSPACE_ID
from invoice_pipeline.line_items.extractor import extract_rich_line_items
from invoice_pipeline.llm.override import ProviderOverride
from invoice_pipeline.schemas import Document, DocumentType
from invoice_pipeline.stages.canonicalize import canonicalize
from invoice_pipeline.stages.classify import classify
from invoice_pipeline.stages.confidence_score import ground_fields
from invoice_pipeline.stages.field_extract import field_extract
from invoice_pipeline.stages.ingest import ingest
from invoice_pipeline.stages.notify import notify
from invoice_pipeline.stages.persist import persist
from invoice_pipeline.stages.text_extract import text_extract
from invoice_pipeline.stages.validate import validate
from invoice_pipeline.templates.detect import apply_vendor_templates
from invoice_pipeline.templates.learner import learn_vendor_template

log = structlog.get_logger()


async def run_pipeline(
    filename: str,
    file_bytes: bytes,
    mime_type: str,
    session: AsyncSession,
    llm_override: ProviderOverride | None = None,
    workspace_id: str = LEGACY_WORKSPACE_ID,
) -> Document:
    t0 = time.monotonic()

    doc = await ingest(filename, file_bytes, mime_type, workspace_id)
    doc = await classify(doc)
    doc = await text_extract(doc)

    if doc.doc_type in (DocumentType.SCANNED_PDF, DocumentType.IMAGE):
        doc = await _ocr_fallback(doc)

    if doc.raw_text.strip():
        doc = await apply_vendor_templates(doc, session)
        doc = await field_extract(doc, override=llm_override)
        doc = await ground_fields(doc)

    if doc.extracted is not None:
        doc = await canonicalize(doc, session)

        # Phase 4: Extract rich line items with math validation
        rich_items, math_errors = extract_rich_line_items(doc)
        if rich_items and doc.extracted is not None:
            updated_invoice = doc.extracted.model_copy(
                update={"rich_line_items": rich_items}
            )
            doc = doc.model_copy(update={"extracted": updated_invoice})

        engine = ConfidenceEngine()
        confidence_breakdown = await engine.compute(doc)

        doc, validation_report = await validate(doc, session)

        canon = doc.canonicalized
        if canon:
            reasons = list(canon.review_reasons)
            needs_review = canon.needs_review
            if confidence_breakdown.needs_review:
                needs_review = True
                reasons.append(f"Confidence score {confidence_breakdown.overall_confidence:.2f} < 0.75")
            # Add math validation errors from Phase 4
            if math_errors:
                needs_review = True
                reasons.extend(math_errors)
            canon = canon.model_copy(update={"needs_review": needs_review, "review_reasons": reasons})

        doc = doc.model_copy(
            update={
                "canonicalized": canon,
                "validation_report": validation_report.model_dump(),
                "confidence_breakdown": confidence_breakdown.model_dump_summary(),
            }
        )

        # Phase 8: Vendor Template Learning
        await learn_vendor_template(doc, session)

    doc = await persist(doc, session)
    doc = await notify(doc)

    elapsed = (time.monotonic() - t0) * 1000
    log.info(
        "pipeline_complete",
        document_id=doc.document_id,
        status=doc.status.value,
        elapsed_ms=round(elapsed),
        errors=len(doc.errors),
    )
    return doc


async def _ocr_fallback(doc: Document) -> Document:
    try:
        from invoice_pipeline.stages.ocr_fallback import ocr_fallback

        return await ocr_fallback(doc)
    except ImportError:
        return doc
    except Exception as exc:
        from invoice_pipeline.schemas import PipelineError

        error = PipelineError(stage="ocr_fallback", message=str(exc))
        return doc.model_copy(update={"errors": [*doc.errors, error]})
