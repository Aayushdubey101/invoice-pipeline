import structlog

from invoice_pipeline.config import OCREngineName, settings
from invoice_pipeline.schemas import Document, Page, PipelineError
from invoice_pipeline.ocr.orchestrator import OCROrchestrator

log = structlog.get_logger()


async def ocr_fallback(doc: Document) -> Document:
    try:
        orchestrator = OCROrchestrator()
        pages, _preprocessed = await orchestrator.extract_pages(doc.file_bytes, doc.mime_type)

        raw_text = "\n\n".join(p.text for p in pages)

        log.info(
            "pipeline_stage",
            stage="ocr_fallback",
            document_id=doc.document_id,
            engine=settings.OCR_ENGINE.value,
            pages=len(pages),
            chars=len(raw_text),
        )
        return doc.model_copy(update={"pages": pages, "raw_text": raw_text})
    except Exception as exc:
        log.error(
            "pipeline_stage_error",
            stage="ocr_fallback",
            document_id=doc.document_id,
            error=str(exc),
        )
        is_fatal = not bool(doc.raw_text.strip())
        error = PipelineError(stage="ocr_fallback", message=str(exc), fatal=is_fatal)
        return doc.model_copy(update={"errors": [*doc.errors, error]})
