import structlog

from invoice_pipeline.llm.factory import create_provider, get_provider
from invoice_pipeline.llm.override import ProviderOverride
from invoice_pipeline.llm.prompts import EXTRACTION_SYSTEM_PROMPT
from invoice_pipeline.schemas import Document, DocumentStatus, Invoice, PipelineError

log = structlog.get_logger()


async def field_extract(doc: Document, override: ProviderOverride | None = None) -> Document:
    if not doc.raw_text.strip():
        error = PipelineError(stage="field_extract", message="No text to extract from")
        return doc.model_copy(update={"errors": [*doc.errors, error]})

    provider = await create_provider(override) if override else await get_provider()
    try:
        result, meta = await provider.extract(
            text=doc.raw_text,
            schema=Invoice,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            temperature=0.0,
        )
    except Exception as exc:
        # Groq is the fast/cheap default; on any failure (rate limit, model
        # deprecated, transient 5xx) fall back once to Gemini rather than
        # failing the document outright. Only for the server-side default
        # chain — a BYOK override is a deliberate per-session choice, don't
        # silently spend the house Gemini key behind it.
        if override is None and provider.provider_name == "groq":
            log.warning(
                "provider_fallback",
                stage="field_extract",
                document_id=doc.document_id,
                from_provider="groq",
                to_provider="gemini",
                error=str(exc),
            )
            try:
                from invoice_pipeline.llm.gemini_client import GeminiProvider

                result, meta = await GeminiProvider().extract(
                    text=doc.raw_text,
                    schema=Invoice,
                    system_prompt=EXTRACTION_SYSTEM_PROMPT,
                    temperature=0.0,
                )
            except Exception as fallback_exc:
                return _extraction_failed(doc, fallback_exc)
        elif override is None and provider.provider_name == "gemini":
            # Gemini backend can 503 under demand spikes even with a valid
            # key/model. Fall back once to Groq (fast/cheap) rather than
            # failing the document outright.
            log.warning(
                "provider_fallback",
                stage="field_extract",
                document_id=doc.document_id,
                from_provider="gemini",
                to_provider="groq",
                error=str(exc),
            )
            try:
                from invoice_pipeline.llm.groq_client import GroqProvider

                result, meta = await GroqProvider().extract(
                    text=doc.raw_text,
                    schema=Invoice,
                    system_prompt=EXTRACTION_SYSTEM_PROMPT,
                    temperature=0.0,
                )
            except Exception as fallback_exc:
                return _extraction_failed(doc, fallback_exc)
        else:
            return _extraction_failed(doc, exc)

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


def _extraction_failed(doc: Document, exc: Exception) -> Document:
    log.error(
        "pipeline_stage_error",
        stage="field_extract",
        document_id=doc.document_id,
        error=str(exc),
    )
    error = PipelineError(stage="field_extract", message=f"LLM extraction failed: {exc}")
    return doc.model_copy(update={"errors": [*doc.errors, error], "status": DocumentStatus.FAILED})
