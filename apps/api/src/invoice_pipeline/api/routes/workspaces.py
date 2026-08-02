"""Phase 14.2: guest workspace CRUD.

Guest-only for now — creating a workspace needs no identity at all (that's
the point of Guest Mode), and GET/DELETE are self-only (the caller must
already hold the X-Workspace-Id it's asking about). The Clerk-authenticated
path is added in 14.8/14.10.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
import shutil

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.api.deps import get_current_workspace
from invoice_pipeline.api.limiter import limiter
from invoice_pipeline.db.models import (
    AuditLog,
    Batch,
    Document,
    ExportHistory,
    Invoice,
    ReviewerFeedback,
    Vendor,
    VendorTemplate,
    Workspace,
)
from invoice_pipeline.db.session import get_session
from invoice_pipeline.services.workspace_lifecycle import purge_workspace_data
from invoice_pipeline.utils.storage import upload_dir
from invoice_pipeline.utils.encryption import encrypt

router = APIRouter()

class MigrateRequest(BaseModel):
    guest_workspace_id: str

class ProviderPreferenceUpdate(BaseModel):
    preference: dict[str, Any]
    api_key: str | None = None

GUEST_WORKSPACE_TTL = timedelta(hours=1)


def _workspace_row(ws: Workspace) -> dict[str, Any]:
    return {
        "id": ws.id,
        "workspace_type": ws.workspace_type,
        "status": ws.status,
        "expires_at": ws.expires_at.isoformat() if ws.expires_at else None,
        "created_at": ws.created_at.isoformat(),
        "trial_uses_remaining": ws.trial_uses_remaining,
    }


@router.post("", status_code=201)
@limiter.limit("30/minute")
async def create_guest_workspace(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ws = Workspace(
        workspace_type="guest",
        expires_at=datetime.now(timezone.utc) + GUEST_WORKSPACE_TTL,
    )
    session.add(ws)
    await session.commit()
    return _workspace_row(ws)


@router.get("/me")
async def get_my_workspace(
    current: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Resolve the caller's own workspace id — guest (via X-Workspace-Id) or
    authenticated (via Bearer). The frontend has no other way to learn its
    authenticated workspace id, since that id is never chosen client-side."""
    return _workspace_row(current)


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    current: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    if current.id != workspace_id:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _workspace_row(current)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    current: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_session),
) -> None:
    if current.id != workspace_id:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await purge_workspace_data(workspace_id, session)


@router.get("/{workspace_id}/provider-preference")
async def get_provider_preference(
    workspace_id: str,
    current: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    if current.id != workspace_id:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    prefs = current.provider_preference or {}
    has_saved_api_key = "encrypted_api_key" in prefs
    
    # Never return the encrypted key to the frontend
    safe_prefs = {k: v for k, v in prefs.items() if k != "encrypted_api_key"}
    safe_prefs["has_saved_api_key"] = has_saved_api_key
    
    return safe_prefs


@router.patch("/{workspace_id}/provider-preference")
async def update_provider_preference(
    workspace_id: str,
    payload: ProviderPreferenceUpdate,
    current: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if current.id != workspace_id:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    prefs = payload.preference.copy()
    
    # If the user provided an API key and is in an authenticated workspace, save it encrypted
    if payload.api_key and current.workspace_type == "authenticated":
        prefs["encrypted_api_key"] = encrypt(payload.api_key)
    # If they are just updating preferences without changing the key, preserve the old key
    elif current.provider_preference and "encrypted_api_key" in current.provider_preference:
        prefs["encrypted_api_key"] = current.provider_preference["encrypted_api_key"]
    
    current.provider_preference = prefs
    await session.commit()
    
    has_saved_api_key = "encrypted_api_key" in prefs
    safe_prefs = {k: v for k, v in prefs.items() if k != "encrypted_api_key"}
    safe_prefs["has_saved_api_key"] = has_saved_api_key
    
    return safe_prefs

@router.post("/migrate")
async def migrate_workspace(
    req: MigrateRequest,
    current: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    if current.workspace_type != "authenticated":
        raise HTTPException(status_code=403, detail="Must be authenticated to migrate workspaces")

    # Fetch guest workspace
    stmt = select(Workspace).where(Workspace.id == req.guest_workspace_id)
    result = await session.execute(stmt)
    guest_ws = result.scalar_one_or_none()

    if not guest_ws:
        raise HTTPException(status_code=404, detail="Guest workspace not found")
    if guest_ws.workspace_type != "guest":
        raise HTTPException(status_code=400, detail="Cannot migrate a non-guest workspace")
    
    # Check expiry logic, SQLite dates need to be normalized
    expires_at = guest_ws.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Guest workspace has expired")

    guest_id = guest_ws.id
    auth_id = current.id

    # Update all scoped tables
    models_to_update = [
        ReviewerFeedback, AuditLog, Invoice, VendorTemplate, Document, Vendor, Batch, ExportHistory
    ]
    for model in models_to_update:
        await session.execute(
            update(model)
            .where(model.workspace_id == guest_id)
            .values(workspace_id=auth_id)
        )
    
    # Delete the guest workspace
    await session.execute(delete(Workspace).where(Workspace.id == guest_id))
    
    await session.commit()

    # Move files
    guest_dir = upload_dir(guest_id)
    auth_dir = upload_dir(auth_id)
    
    if guest_dir.exists():
        shutil.copytree(guest_dir, auth_dir, dirs_exist_ok=True)
        shutil.rmtree(guest_dir, ignore_errors=True)

    return {"status": "success", "migrated_from": guest_id, "migrated_to": auth_id}
