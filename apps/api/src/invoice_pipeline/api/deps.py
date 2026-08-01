from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.auth.clerk import ClerkTokenInvalid, verify_clerk_token
from invoice_pipeline.db.models import Workspace
from invoice_pipeline.db.session import get_session


async def db(session: AsyncSession = Depends(get_session)) -> AsyncGenerator[AsyncSession, None]:
    yield session


async def _get_or_create_authenticated_workspace(
    clerk_user_id: str, session: AsyncSession
) -> Workspace:
    result = await session.execute(
        select(Workspace).where(Workspace.clerk_user_id == clerk_user_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is not None:
        return workspace

    workspace = Workspace(workspace_type="authenticated", clerk_user_id=clerk_user_id)
    session.add(workspace)
    await session.commit()
    await session.refresh(workspace)
    return workspace


async def get_current_workspace(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Workspace:
    """Resolve the calling workspace from the request.

    Authorization: Bearer is tried first (Clerk-verified, authenticated
    workspace — get-or-create by clerk_user_id, never expires). Falls back
    to X-Workspace-Id (guest, added in 14.2) when no bearer token is present.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ")
        try:
            clerk_user_id = await verify_clerk_token(token)
        except ClerkTokenInvalid as exc:
            raise HTTPException(status_code=401, detail=f"Invalid Clerk token: {exc}") from exc
        return await _get_or_create_authenticated_workspace(clerk_user_id, session)

    workspace_id = request.headers.get("X-Workspace-Id")
    if not workspace_id:
        raise HTTPException(status_code=401, detail="X-Workspace-Id header is required")

    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=401, detail="Unknown workspace")
    if workspace.workspace_type != "guest":
        raise HTTPException(status_code=401, detail="Invalid workspace")
    if workspace.status != "active":
        raise HTTPException(status_code=401, detail="Workspace session has ended")
    expires_at = workspace.expires_at
    if expires_at is not None:
        # sqlite (used in tests) doesn't round-trip tzinfo on DateTime(timezone=True)
        # columns — a naive value read back from it is always UTC, since that's the
        # only thing ever written to this column.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Workspace session has expired")

    return workspace
