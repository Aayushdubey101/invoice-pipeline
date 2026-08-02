"""
Phase 11 — Batch Upload & Processing

Supports:
  - Single or multiple file upload in one request
  - Folder upload (multiple files sent together)
  - Drag & drop (handled on frontend)
  - Optional ZIP support stub
  - Supported types: PDF, PNG, JPG, JPEG, TIFF

Each file enters the existing pipeline independently.
Failed files are logged; remaining files continue processing.
A Batch ID is generated per upload group.
"""
import hashlib
import mimetypes
import time
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from invoice_pipeline.api.deps import get_current_workspace
from invoice_pipeline.api.limiter import limiter
from invoice_pipeline.config import settings
from invoice_pipeline.db import models
from invoice_pipeline.db.models import LEGACY_WORKSPACE_ID, Workspace
from invoice_pipeline.db.session import async_session_factory, get_session
from invoice_pipeline.llm.override import ProviderOverride, parse_provider_override
from invoice_pipeline.pipeline import run_pipeline
from invoice_pipeline.services.trial import TRIAL_EXHAUSTED_MESSAGE, consume_trial_use
from invoice_pipeline.stages.ingest import ALLOWED_MIME_TYPES
from invoice_pipeline.utils.storage import upload_dir

log = structlog.get_logger()
router = APIRouter()


def _batch_summary(batch: models.Batch) -> dict[str, Any]:
    return {
        "batch_id": batch.id,
        "upload_source": batch.upload_source,
        "total_files": batch.total_files,
        "completed": batch.completed,
        "failed": batch.failed,
        "pending": batch.pending,
        "skipped": batch.skipped,
        "avg_confidence": float(batch.avg_confidence) if batch.avg_confidence is not None else None,
        "processing_time_ms": batch.processing_time_ms,
        "created_at": batch.created_at.isoformat(),
    }


@router.post("/upload", status_code=202)
@limiter.limit("10/minute")
async def batch_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile],
    upload_source: str = Query(default="web"),
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """
    Upload one or more files as a batch.

    Returns immediately with a batch_id once the batch row is created — each
    file then enters the AI pipeline independently in the background, so the
    caller isn't blocked on OCR/LLM processing and can resume progress via
    GET /batch/{batch_id} even after a page refresh or navigation.
    """
    # Guard: empty upload is a client error
    if not files:
        return {
            "batch_id": None,
            "upload_source": upload_source,
            "total_files": 0,
            "status": "complete",
        }

    # Guard: upload_source is user-supplied, cap at 32 chars
    upload_source = upload_source[:32]

    # Read all bytes now — UploadFile's stream is only valid for this request,
    # it can't be read from inside the background task.
    file_payloads: list[tuple[str, bytes, str]] = []
    for upload_file in files:
        filename = upload_file.filename or "upload"
        file_bytes = await upload_file.read()
        mime_type = (
            upload_file.content_type
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        file_payloads.append((filename, file_bytes, mime_type))

    # Parse the browser-session provider override here — it's gone once
    # _process_batch_files runs as a BackgroundTasks job with its own DB
    # session and no original request to read headers from.
    llm_override = parse_provider_override(request, workspace)

    batch = models.Batch(
        workspace_id=workspace.id,
        upload_source=upload_source,
        total_files=len(files),
        pending=len(files),
    )
    session.add(batch)
    await session.commit()  # must be durable before the background task looks it up

    background_tasks.add_task(
        _process_batch_files, batch.id, file_payloads, llm_override, workspace.id
    )

    log.info("batch_upload_accepted", batch_id=batch.id, total_files=len(files))
    return {
        "batch_id": batch.id,
        "upload_source": upload_source,
        "total_files": len(files),
        "status": "processing",
    }


async def _process_batch_files(
    batch_id: str,
    file_payloads: list[tuple[str, bytes, str]],
    override: ProviderOverride | None = None,
    workspace_id: str = LEGACY_WORKSPACE_ID,
) -> None:
    """Runs after the upload response is sent. Uses its own DB session — the
    request-scoped session is closed by the time a background task runs."""
    t0 = time.monotonic()
    batch_upload_dir = upload_dir(workspace_id)

    async with async_session_factory() as session:
        batch = await session.get(models.Batch, batch_id)
        if batch is None:
            log.error("batch_process_missing_batch", batch_id=batch_id)
            return

        confidences: list[float] = []
        completed = failed = skipped = 0

        async def _sync_batch_counts() -> None:
            batch.completed = completed
            batch.failed = failed
            batch.skipped = skipped
            batch.pending = max(0, batch.total_files - completed - failed - skipped)
            await session.commit()

        for filename, file_bytes, mime_type in file_payloads:
            # Size guard
            if len(file_bytes) > settings.max_upload_bytes:
                skipped += 1
                await _sync_batch_counts()
                continue

            # MIME type guard
            if mime_type not in ALLOWED_MIME_TYPES:
                skipped += 1
                await _sync_batch_counts()
                continue

            # Trial guard: only meters calls falling back to the platform's
            # own .env key — a request carrying its own BYOK override skips this.
            if override is None and not await consume_trial_use(workspace_id, session):
                doc_id = hashlib.sha256(file_bytes + workspace_id.encode()).hexdigest()
                (batch_upload_dir / doc_id).write_bytes(file_bytes)
                existing = await session.get(models.Document, doc_id)
                trial_error = [{"stage": "trial_limit", "message": TRIAL_EXHAUSTED_MESSAGE, "fatal": True}]
                if existing is None:
                    session.add(
                        models.Document(
                            id=doc_id,
                            workspace_id=workspace_id,
                            filename=filename,
                            mime_type=mime_type,
                            file_size_bytes=len(file_bytes),
                            status="failed",
                            errors=trial_error,
                            batch_id=batch_id,
                        )
                    )
                else:
                    existing.status = "failed"
                    existing.errors = trial_error
                    existing.batch_id = batch_id
                failed += 1
                await _sync_batch_counts()
                continue

            try:
                doc = await run_pipeline(
                    filename=filename,
                    file_bytes=file_bytes,
                    mime_type=mime_type,
                    session=session,
                    llm_override=override,
                    workspace_id=workspace_id,
                )

                # Attach batch to document record
                db_doc = await session.get(models.Document, doc.document_id)
                if db_doc is not None:
                    db_doc.batch_id = batch_id

                # Persist file bytes to disk for later retrieval / retry
                (batch_upload_dir / doc.document_id).write_bytes(file_bytes)

                # Collect confidence for batch average
                if doc.confidence_breakdown:
                    conf = doc.confidence_breakdown.get("overall_score")
                    if conf is not None:
                        confidences.append(float(conf))

                # Stage-level failures land in doc.status == "failed" without raising
                # (pipeline stages never raise); count those as failed, not completed.
                if doc.status.value == "failed":
                    failed += 1
                else:
                    completed += 1

            except Exception as exc:
                # Safety net for the rare case a stage raises before reaching persist()
                # (e.g. ingest() rejecting the file) — nothing has been committed yet.
                log.error("batch_file_failed", filename=filename, error=str(exc), batch_id=batch_id)
                await session.rollback()
                batch = await session.get(models.Batch, batch_id)  # rollback expires it

                doc_id = hashlib.sha256(file_bytes + workspace_id.encode()).hexdigest()
                (batch_upload_dir / doc_id).write_bytes(file_bytes)
                existing = await session.get(models.Document, doc_id)
                failure_errors = [{"stage": "pipeline", "message": str(exc), "fatal": True}]
                if existing is None:
                    session.add(
                        models.Document(
                            id=doc_id,
                            workspace_id=workspace_id,
                            filename=filename,
                            mime_type=mime_type,
                            file_size_bytes=len(file_bytes),
                            status="failed",
                            errors=failure_errors,
                            batch_id=batch_id,
                        )
                    )
                else:
                    existing.status = "failed"
                    existing.errors = failure_errors
                    existing.batch_id = batch_id

                failed += 1

            await _sync_batch_counts()

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        avg_confidence: float | None = sum(confidences) / len(confidences) if confidences else None

        batch.completed = completed
        batch.failed = failed
        batch.skipped = skipped
        batch.pending = 0
        batch.avg_confidence = avg_confidence  # type: ignore[assignment]
        batch.processing_time_ms = elapsed_ms

        await session.commit()
        log.info(
            "batch_complete", batch_id=batch_id, completed=completed, failed=failed, elapsed_ms=elapsed_ms
        )


@router.get("/")
async def list_batches(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """List batches with pagination."""
    result = await session.execute(
        select(models.Batch)
        .where(models.Batch.workspace_id == workspace.id)
        .order_by(models.Batch.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    batches = result.scalars().all()
    total = (
        await session.execute(
            select(func.count(models.Batch.id)).where(models.Batch.workspace_id == workspace.id)
        )
    ).scalar_one()
    return {"batches": [_batch_summary(b) for b in batches], "total": total}


@router.get("/{batch_id}")
async def get_batch(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Get batch details including all associated documents."""
    batch = await session.get(models.Batch, batch_id)
    if batch is None or batch.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Batch not found")

    docs_result = await session.execute(
        select(models.Document)
        .where(models.Document.batch_id == batch_id)
        .options(selectinload(models.Document.invoice))
        .order_by(models.Document.created_at.asc())
    )
    docs = docs_result.scalars().all()

    return {
        **_batch_summary(batch),
        "documents": [
            {
                "document_id": d.id,
                "filename": d.filename,
                "status": d.status,
                "errors": d.errors,
                "invoice_id": d.invoice.id if d.invoice else None,
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ],
    }


@router.post("/{batch_id}/retry-failed", status_code=202)
async def retry_failed(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Retry all failed documents in a batch."""
    batch = await session.get(models.Batch, batch_id)
    if batch is None or batch.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Batch not found")

    docs_result = await session.execute(
        select(models.Document)
        .where(models.Document.batch_id == batch_id)
        .where(models.Document.status == "failed")
    )
    failed_docs = docs_result.scalars().all()

    if not failed_docs:
        return {"batch_id": batch_id, "retried": 0, "message": "No failed documents to retry"}

    batch_upload_dir = upload_dir(workspace.id)
    retried = 0
    retry_succeeded = 0
    retry_failed_count = 0

    for db_doc in failed_docs:
        file_path = batch_upload_dir / db_doc.id
        if not file_path.exists():
            log.warning("batch_retry_file_missing", document_id=db_doc.id)
            retry_failed_count += 1
            continue
        # Guard: mime_type must be known
        mime_type = db_doc.mime_type or "application/pdf"
        try:
            file_bytes = file_path.read_bytes()
            doc = await run_pipeline(
                filename=db_doc.filename,
                file_bytes=file_bytes,
                mime_type=mime_type,
                session=session,
                workspace_id=workspace.id,
            )
            retried += 1
            # A retry can still land back on status == "failed" without raising
            # (pipeline stages never raise) — only count it a success if it didn't.
            if doc.status.value == "failed":
                retry_failed_count += 1
            else:
                retry_succeeded += 1
        except Exception as exc:
            log.error("batch_retry_failed", document_id=db_doc.id, error=str(exc))
            retried += 1
            retry_failed_count += 1

    # Update batch counts after retry
    if retry_succeeded > 0:
        batch.completed = (batch.completed or 0) + retry_succeeded
        batch.failed = max(0, (batch.failed or 0) - retry_succeeded)

    await session.commit()
    return {"batch_id": batch_id, "retried": retried, "succeeded": retry_succeeded, "still_failed": retry_failed_count}
