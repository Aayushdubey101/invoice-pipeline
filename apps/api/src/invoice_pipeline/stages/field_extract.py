import structlog

from invoice_pipeline.llm.factory import get_provider
from invoice_pipeline.llm.prompts import EXTRACTION_SYSTEM_PROMPT
from invoice_pipeline.schemas import Document, DocumentStatus, Invoice, PipelineError

log = structlog.get_logger()


async def field_extract(doc: Document) -> Document:
    if not doc.raw_text.strip():
        error = PipelineError(stage="field_extract", message="No text to extract from")
        return doc.model_copy(update={"errors": [*doc.errors, error]})

    try:
        provider = await get_provider()
        result, meta = await provider.extract(
            text=doc.raw_text,
            schema=Invoice,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            temperature=0.0,
        )
        invoice: Invoice = result  # type: ignore[assignment]
        log.info(
            "pipeline_stage",
            stage="field_extract",
            document_id=doc.document_id,
            provider=meta.provider_name,
            model=meta.model_name,
            latency_ms=meta.latency_ms,
            tokens_in=meta.tokens_in,
            tokens_out=meta.tokens_out,
        )
        return doc.model_copy(update={"extracted": invoice})
    except Exception as exc:
        log.error("pipeline_stage_error", stage="field_extract", document_id=doc.document_id, error=str(exc))
        error = PipelineError(stage="field_extract", message=f"LLM extraction failed: {exc}")
        return doc.model_copy(update={"errors": [*doc.errors, error], "status": DocumentStatus.FAILED})
