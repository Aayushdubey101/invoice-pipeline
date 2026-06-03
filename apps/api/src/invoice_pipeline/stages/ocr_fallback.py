import structlog

from invoice_pipeline.config import OCREngineName, settings
from invoice_pipeline.ocr.base import OCREngine
from invoice_pipeline.schemas import Document, Page, PipelineError

log = structlog.get_logger()


async def ocr_fallback(doc: Document) -> Document:
    try:
        pages = await _extract_with_fallback(doc)
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


def _load_engine(allow_paddle: bool = True) -> OCREngine:
    if allow_paddle and settings.OCR_ENGINE == OCREngineName.PADDLEOCR:
        try:
            from invoice_pipeline.ocr.paddle import PaddleOCREngine

            return PaddleOCREngine()
        except ImportError:
            log.warning("ocr_engine_fallback", reason="paddleocr not installed, using tesseract")

    from invoice_pipeline.ocr.tesseract import TesseractEngine

    return TesseractEngine()


async def _extract_with_fallback(doc: Document) -> list[Page]:
    engine = _load_engine()
    try:
        return await engine.extract_pages(doc.file_bytes, doc.mime_type)
    except (ImportError, ModuleNotFoundError):
        log.warning(
            "ocr_engine_runtime_fallback",
            reason="paddleocr unavailable at runtime, using tesseract",
        )
        engine = _load_engine(allow_paddle=False)
        return await engine.extract_pages(doc.file_bytes, doc.mime_type)
