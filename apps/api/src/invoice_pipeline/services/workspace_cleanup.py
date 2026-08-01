"""Phase 14.7: hourly guest-workspace cleanup.

Finds expired guest workspaces and purges each in its own session — mirrors
batch.py::_process_batch_files' pattern of opening a fresh session outside
request scope, since this runs from APScheduler, not a request.
"""

from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from invoice_pipeline.db.models import Workspace
from invoice_pipeline.db.session import async_session_factory
from invoice_pipeline.services.workspace_lifecycle import purge_workspace_data

log = structlog.get_logger()


async def run_cleanup() -> None:
    async with async_session_factory() as session:
        rows = (
            await session.execute(select(Workspace.id, Workspace.expires_at).where(Workspace.workspace_type == "guest"))
        ).all()

    now = datetime.now(timezone.utc)
    expired_ids = []
    for workspace_id, expires_at in rows:
        if expires_at is None:
            continue
        # sqlite (used in tests) doesn't round-trip tzinfo on DateTime(timezone=True).
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            expired_ids.append(workspace_id)

    for workspace_id in expired_ids:
        async with async_session_factory() as session:
            await purge_workspace_data(workspace_id, session)

    if expired_ids:
        log.info("workspace_cleanup_run", purged_count=len(expired_ids))
