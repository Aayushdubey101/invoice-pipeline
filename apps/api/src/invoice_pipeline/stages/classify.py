import io

import structlog

from invoice_pipeline.config import settings
from invoice_pipeline.schemas import Document, DocumentType, PipelineError

log = structlog.get_logger()


async def classify(doc: Document) -> Document:
    try:
        doc_type = _detect_type(doc)
        log.info(
            "pipeline_stage",
            stage="classify",
            document_id=doc.document_id,
            doc_type=doc_type,
        )
        return doc.model_copy(update={"doc_type": doc_type})
    except Exception as exc:
        log.error(
            "pipeline_stage_error", stage="classify", document_id=doc.document_id, error=str(exc)
        )
        error = PipelineError(stage="classify", message=str(exc))
        return doc.model_copy(update={"errors": [*doc.errors, error]})


def _detect_type(doc: Document) -> DocumentType:
    mime = doc.mime_type

    if mime in ("image/png", "image/jpeg", "image/tiff"):
        return DocumentType.IMAGE

    if mime in ("message/rfc822", "application/vnd.ms-outlook"):
        return DocumentType.EMAIL

    if mime in ("text/html", "text/plain"):
        return DocumentType.TEXT_PDF  # treat as text path

    if mime == "application/pdf":
        return _classify_pdf(doc.file_bytes)

    return DocumentType.UNKNOWN


def _classify_pdf(file_bytes: bytes) -> DocumentType:
    """Heuristic: if avg chars/page < threshold, assume scanned."""
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if not pdf.pages:
                return DocumentType.SCANNED_PDF
            total_chars = sum(len(p.extract_text() or "") for p in pdf.pages)
            avg = total_chars / len(pdf.pages)
            return (
                DocumentType.TEXT_PDF
                if avg >= settings.SCANNED_PDF_CHARS_PER_PAGE_THRESHOLD
                else DocumentType.SCANNED_PDF
            )
    except Exception:
        return DocumentType.SCANNED_PDF
