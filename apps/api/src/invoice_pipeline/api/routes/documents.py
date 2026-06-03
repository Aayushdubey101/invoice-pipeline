import hashlib
import mimetypes
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from invoice_pipeline.api.metrics import UPLOAD_ERRORS_TOTAL, UPLOADS_TOTAL
from invoice_pipeline.db import models
from invoice_pipeline.db.session import get_session
from invoice_pipeline.pipeline import run_pipeline

log = structlog.get_logger()
router = APIRouter()

_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload", status_code=202)
async def upload_document(
    request: Request,
    file: UploadFile,
    force_reprocess: bool = Query(False),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    mime_type = (
        file.content_type
        or mimetypes.guess_type(file.filename or "")[0]
        or "application/octet-stream"
    )
    filename = file.filename or "upload"

    doc_id = hashlib.sha256(file_bytes).hexdigest()
    existing = await session.get(models.Document, doc_id)
    already_clean = (
        existing is not None
        and existing.status == "complete"
        and not existing.errors
        and not force_reprocess
    )
    if existing is not None and already_clean:
        return {
            "document_id": existing.id,
            "status": existing.status,
            "errors": existing.errors,
        }

    UPLOADS_TOTAL.inc()
    try:
        doc = await run_pipeline(
            filename=filename,
            file_bytes=file_bytes,
            mime_type=mime_type,
            session=session,
        )

        # Save file bytes to disk so they can be retrieved by the frontend via /documents/{id}/file
        upload_dir = Path(__file__).resolve().parents[4] / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / doc.document_id
        with open(file_path, "wb") as f:
            f.write(file_bytes)

    except ValueError as exc:
        UPLOAD_ERRORS_TOTAL.inc()
        raise HTTPException(status_code=422, detail=str(exc))

    if doc.errors:
        UPLOAD_ERRORS_TOTAL.inc()

    return {
        "document_id": doc.document_id,
        "status": doc.status.value,
        "errors": [e.model_dump() for e in doc.errors],
    }


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    db_doc = await session.get(models.Document, document_id)
    if db_doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    upload_dir = Path(__file__).resolve().parents[4] / "data" / "uploads"
    file_path = upload_dir / document_id

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File content not found on disk")

    return FileResponse(
        path=file_path,
        media_type=db_doc.mime_type,
        filename=db_doc.filename,
    )


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = (
        select(models.Document)
        .options(selectinload(models.Document.invoice))
        .where(models.Document.id == document_id)
    )
    db_doc = (await session.execute(stmt)).scalar_one_or_none()
    if db_doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    result: dict[str, Any] = {
        "document_id": db_doc.id,
        "filename": db_doc.filename,
        "mime_type": db_doc.mime_type,
        "doc_type": db_doc.doc_type,
        "status": db_doc.status,
        "errors": db_doc.errors,
        "created_at": db_doc.created_at.isoformat(),
    }

    if db_doc.invoice:
        inv = db_doc.invoice
        result["invoice"] = {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "invoice_date": inv.invoice_date,
            "due_date": inv.due_date,
            "buyer_name": inv.buyer_name,
            "total_amount": str(inv.total_amount) if inv.total_amount else None,
            "currency": inv.currency,
            "needs_review": inv.needs_review,
            "review_reasons": inv.review_reasons,
        }

    return result
