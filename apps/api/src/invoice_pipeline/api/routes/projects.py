"""
Phase 14.11 — Project (Batch) CRUD for authenticated users.
"""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from invoice_pipeline.api.deps import get_current_workspace
from invoice_pipeline.db import models
from invoice_pipeline.db.models import Workspace
from invoice_pipeline.db.session import get_session

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str


class ProjectRename(BaseModel):
    name: str


def _project_summary(batch: models.Batch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "name": batch.name,
        "is_archived": batch.is_archived,
        "archived_at": batch.archived_at.isoformat() if batch.archived_at else None,
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


@router.post("")
async def create_project(
    payload: ProjectCreate,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Create a new empty project (batch)."""
    batch = models.Batch(
        workspace_id=workspace.id,
        name=payload.name,
        upload_source="web",  # default
    )
    session.add(batch)
    await session.commit()
    return _project_summary(batch)


@router.get("")
async def list_projects(
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[dict[str, Any]]:
    """List projects, excluding archived by default."""
    stmt = select(models.Batch).where(models.Batch.workspace_id == workspace.id)
    if not include_archived:
        stmt = stmt.where(models.Batch.is_archived == False)
    stmt = stmt.order_by(models.Batch.created_at.desc())
    
    result = await session.execute(stmt)
    batches = result.scalars().all()
    return [_project_summary(b) for b in batches]


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Get project details including document summaries."""
    batch = await session.get(models.Batch, project_id)
    if batch is None or batch.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Project not found")

    docs_result = await session.execute(
        select(models.Document)
        .where(models.Document.batch_id == project_id)
        .options(selectinload(models.Document.invoice))
        .order_by(models.Document.created_at.asc())
    )
    docs = docs_result.scalars().all()

    summary = _project_summary(batch)
    summary["documents"] = [
        {
            "document_id": d.id,
            "filename": d.filename,
            "status": d.status,
            "invoice_id": d.invoice.id if d.invoice else None,
            "created_at": d.created_at.isoformat(),
        }
        for d in docs
    ]
    return summary


@router.patch("/{project_id}")
async def rename_project(
    project_id: str,
    payload: ProjectRename,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Rename a project."""
    batch = await session.get(models.Batch, project_id)
    if batch is None or batch.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Project not found")

    batch.name = payload.name
    await session.commit()
    return _project_summary(batch)


@router.post("/{project_id}/duplicate")
async def duplicate_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Duplicate a project (creates an empty shell)."""
    batch = await session.get(models.Batch, project_id)
    if batch is None or batch.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Project not found")

    # Create empty shell with (Copy) appended to name
    base_name = batch.name or "Project"
    new_name = f"{base_name} (Copy)"
    
    new_batch = models.Batch(
        workspace_id=workspace.id,
        name=new_name,
        upload_source=batch.upload_source,
    )
    session.add(new_batch)
    await session.commit()
    return _project_summary(new_batch)


@router.post("/{project_id}/archive")
async def archive_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Archive a project."""
    batch = await session.get(models.Batch, project_id)
    if batch is None or batch.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if not batch.is_archived:
        batch.is_archived = True
        batch.archived_at = datetime.now(timezone.utc)
        await session.commit()

    return _project_summary(batch)


@router.post("/{project_id}/unarchive")
async def unarchive_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Unarchive a project."""
    batch = await session.get(models.Batch, project_id)
    if batch is None or batch.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if batch.is_archived:
        batch.is_archived = False
        batch.archived_at = None
        await session.commit()

    return _project_summary(batch)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> None:
    """Hard-delete a project (must be archived first)."""
    batch = await session.get(models.Batch, project_id)
    if batch is None or batch.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if not batch.is_archived:
        raise HTTPException(status_code=400, detail="Project must be archived before deletion")

    await session.delete(batch)
    await session.commit()
