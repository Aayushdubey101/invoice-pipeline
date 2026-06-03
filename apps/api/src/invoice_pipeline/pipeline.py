"""
Pipeline orchestrator. Chains all stages.
Invariant: stages NEVER raise — errors attach to document.errors[].
"""

import time

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.schemas import Document, DocumentType
from invoice_pipeline.stages.canonicalize import canonicalize
from invoice_pipeline.stages.classify import classify
from invoice_pipeline.stages.confidence_score import score_confidence
from invoice_pipeline.stages.field_extract import field_extract
from invoice_pipeline.stages.ingest import ingest
from invoice_pipeline.stages.notify import notify
from invoice_pipeline.stages.persist import persist
from invoice_pipeline.stages.text_extract import text_extract

log = structlog.get_logger()


async def run_pipeline(
    filename: str,
    file_bytes: bytes,
    mime_type: str,
    session: AsyncSession,
) -> Document:
    t0 = time.monotonic()

    doc = await ingest(filename, file_bytes, mime_type)
    doc = await classify(doc)
    doc = await text_extract(doc)

    if doc.doc_type in (DocumentType.SCANNED_PDF, DocumentType.IMAGE):
        doc = await _ocr_fallback(doc)

    if doc.raw_text.strip():
        doc = await field_extract(doc)

    if doc.extracted is not None:
        doc = await canonicalize(doc, session)
        doc = await score_confidence(doc)

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
