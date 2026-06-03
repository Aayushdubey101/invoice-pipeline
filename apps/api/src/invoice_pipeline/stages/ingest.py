import hashlib

import structlog

from invoice_pipeline.schemas import Document, DocumentStatus, PipelineError

log = structlog.get_logger()

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "message/rfc822",
    "application/vnd.ms-outlook",
    "text/html",
    "text/plain",
}


async def ingest(filename: str, file_bytes: bytes, mime_type: str) -> Document:
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported MIME type: {mime_type}")

    document_id = hashlib.sha256(file_bytes).hexdigest()

    log.info(
        "pipeline_stage",
        stage="ingest",
        document_id=document_id,
        filename=filename,
        mime_type=mime_type,
        file_size=len(file_bytes),
    )

    return Document(
        document_id=document_id,
        filename=filename,
        mime_type=mime_type,
        file_bytes=file_bytes,
        status=DocumentStatus.PROCESSING,
    )
