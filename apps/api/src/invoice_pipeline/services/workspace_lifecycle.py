"""Phase 14: shared workspace deletion logic.

One function, reused verbatim by DELETE /workspaces/{id}, POST /session/finish
(14.6), and the hourly guest-cleanup job (14.7) — write once here, never
duplicate the delete-order/disk-cleanup logic at each call site.

Deletion order matters: no table in this schema has cascade/ondelete rules
(confirmed in Phase 14 planning research), so children must be deleted before
parents. InvoiceField/LineItem have no workspace_id of their own (they inherit
scoping via their parent Invoice), so they're targeted through a subquery.
"""

import shutil

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.db.models import (
    AuditLog,
    Batch,
    Document,
    ExportHistory,
    Invoice,
    InvoiceField,
    LineItem,
    ReviewerFeedback,
    Vendor,
    VendorTemplate,
    Workspace,
)
from invoice_pipeline.utils.storage import upload_dir

log = structlog.get_logger()


async def purge_workspace_data(workspace_id: str, session: AsyncSession) -> None:
    """Delete every row belonging to a workspace, its uploaded files, and the
    Workspace row itself. Idempotent — safe to call on an already-empty
    workspace."""
    workspace_type = await session.scalar(
        select(Workspace.workspace_type).where(Workspace.id == workspace_id)
    )

    invoice_ids = select(Invoice.id).where(Invoice.workspace_id == workspace_id)

    await session.execute(delete(InvoiceField).where(InvoiceField.invoice_id.in_(invoice_ids)))
    await session.execute(delete(LineItem).where(LineItem.invoice_id.in_(invoice_ids)))
    await session.execute(delete(ReviewerFeedback).where(ReviewerFeedback.workspace_id == workspace_id))
    await session.execute(delete(AuditLog).where(AuditLog.workspace_id == workspace_id))
    await session.execute(delete(Invoice).where(Invoice.workspace_id == workspace_id))
    await session.execute(delete(VendorTemplate).where(VendorTemplate.workspace_id == workspace_id))
    await session.execute(delete(Document).where(Document.workspace_id == workspace_id))
    await session.execute(delete(Vendor).where(Vendor.workspace_id == workspace_id))
    await session.execute(delete(Batch).where(Batch.workspace_id == workspace_id))
    await session.execute(delete(ExportHistory).where(ExportHistory.workspace_id == workspace_id))
    await session.execute(delete(Workspace).where(Workspace.id == workspace_id))
    await session.commit()

    shutil.rmtree(upload_dir(workspace_id), ignore_errors=True)

    try:
        from qdrant_client.http import models

        from invoice_pipeline.canonicalizers.qdrant_client import get_qdrant_client
        from invoice_pipeline.config import settings

        client = get_qdrant_client()
        await client.delete(
            collection_name=settings.QDRANT_VENDOR_COLLECTION,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="workspace_id", match=models.MatchValue(value=workspace_id)
                    )
                ]
            ),
        )
    except Exception as exc:
        log.debug("qdrant_vector_deletion_skipped", error=str(exc))

    if workspace_type == "guest":
        from invoice_pipeline.config import reset_runtime_overrides, settings
        from invoice_pipeline.llm import factory

        reset_runtime_overrides(settings)
        factory._provider_instance = None

    log.info("workspace_purged", workspace_id=workspace_id)
