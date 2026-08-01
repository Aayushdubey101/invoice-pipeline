import hashlib

import structlog

from invoice_pipeline.db.models import LEGACY_WORKSPACE_ID
from invoice_pipeline.schemas import Document, DocumentStatus

log = structlog.get_logger()

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",       # non-standard alias for JPEG used by some browsers
    "image/tiff",
    "image/x-tiff",    # alternative TIFF MIME type
    "message/rfc822",
    "application/vnd.ms-outlook",
    "text/html",
    "text/plain",
}


async def ingest(
    filename: str,
    file_bytes: bytes,
    mime_type: str,
    workspace_id: str = LEGACY_WORKSPACE_ID,
) -> Document:
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported MIME type: {mime_type}")

    # Salted with workspace_id so two workspaces uploading byte-identical
    # content never collide on the same Document PK (cross-tenant leak).
    document_id = hashlib.sha256(file_bytes + workspace_id.encode()).hexdigest()

    log.info(
        "pipeline_stage",
        stage="ingest",
        document_id=document_id,
        workspace_id=workspace_id,
        filename=filename,
        mime_type=mime_type,
        file_size=len(file_bytes),
    )

    return Document(
        document_id=document_id,
        workspace_id=workspace_id,
        filename=filename,
        mime_type=mime_type,
        file_bytes=file_bytes,
        status=DocumentStatus.PROCESSING,
    )
