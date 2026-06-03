import httpx
import structlog

from invoice_pipeline.config import settings
from invoice_pipeline.schemas import Document, DocumentStatus, PipelineError

log = structlog.get_logger()


async def notify(doc: Document) -> Document:
    if not settings.REVIEW_WEBHOOK_URL:
        return doc
    if doc.status not in (DocumentStatus.NEEDS_REVIEW, DocumentStatus.COMPLETE):
        return doc
    try:
        payload = {
            "document_id": doc.document_id,
            "status": doc.status.value,
            "needs_review": doc.canonicalized.needs_review if doc.canonicalized else False,
            "review_reasons": doc.canonicalized.review_reasons if doc.canonicalized else [],
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(settings.REVIEW_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
        log.info(
            "pipeline_stage",
            stage="notify",
            document_id=doc.document_id,
            status_code=resp.status_code,
        )
    except Exception as exc:
        log.warning(
            "pipeline_stage_warn", stage="notify", document_id=doc.document_id, error=str(exc)
        )
        # notify failure is non-fatal — attach as warning, don't change status
        error = PipelineError(stage="notify", message=str(exc))
        return doc.model_copy(update={"errors": [*doc.errors, error]})
    return doc
