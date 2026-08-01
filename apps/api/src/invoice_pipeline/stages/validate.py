"""Validation pipeline stage — runs business rule validation on extracted invoices."""

import structlog

from invoice_pipeline.schemas import Document, PipelineError
from invoice_pipeline.validation.engine import ValidationEngine
from invoice_pipeline.validation.models import ValidationReport
from invoice_pipeline.validation.rules.base import ValidationContext

log = structlog.get_logger()


async def validate(doc: Document, session: object | None = None) -> tuple[Document, ValidationReport]:
    """Run all validation rules against the extracted invoice.

    Returns the document (unchanged) and the validation report.
    Never raises — errors are captured in the report.

    Parameters
    ----------
    doc : Document
        Pipeline document with extracted invoice data.
    session : AsyncSession | None
        Optional DB session for rules that need database access
        (e.g. duplicate detection).
    """
    if doc.extracted is None:
        log.info(
            "pipeline_stage",
            stage="validate",
            document_id=doc.document_id,
            skipped=True,
        )
        return doc, ValidationReport()

    try:
        from sqlalchemy.ext.asyncio import AsyncSession

        ctx = ValidationContext(
            document=doc,
            raw_text=doc.raw_text,
            session=session if isinstance(session, AsyncSession) else None,
        )
        engine = ValidationEngine()
        report = await engine.validate(doc.extracted, ctx)

        log.info(
            "pipeline_stage",
            stage="validate",
            document_id=doc.document_id,
            passed=report.passed,
            failed=report.failed,
            warnings=report.warnings,
            is_valid=report.is_valid,
        )
        return doc, report

    except Exception as exc:
        log.error(
            "pipeline_stage_error",
            stage="validate",
            document_id=doc.document_id,
            error=str(exc),
        )
        error = PipelineError(stage="validate", message=str(exc), fatal=False)
        updated = doc.model_copy(update={"errors": [*doc.errors, error]})
        return updated, ValidationReport()
