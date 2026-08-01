"""
Phase 11 — Business Dashboard Stats

Provides aggregate statistics for the dashboard:
  - Invoice counts by status
  - Recent uploads
  - Vendor statistics
  - Batch counts
  - Average confidence
"""
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.api.deps import get_current_workspace
from invoice_pipeline.db import models
from invoice_pipeline.db.models import Workspace
from invoice_pipeline.db.session import get_session

router = APIRouter()


@router.get("/stats")
async def dashboard_stats(
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """
    Returns aggregate stats for the business dashboard:
    - Total invoices, by review status
    - Document processing status counts
    - Average extraction confidence
    - Recent uploads (last 10 documents)
    - Top vendors by invoice count
    - Batch counts
    """
    ws_id = workspace.id

    # Invoice counts
    total_invoices = (
        await session.execute(
            select(func.count(models.Invoice.id)).where(models.Invoice.workspace_id == ws_id)
        )
    ).scalar_one()
    needs_review = (
        await session.execute(
            select(func.count(models.Invoice.id)).where(
                models.Invoice.needs_review == True,  # noqa: E712
                models.Invoice.workspace_id == ws_id,
            )
        )
    ).scalar_one()
    approved = (
        await session.execute(
            select(func.count(models.Invoice.id)).where(
                models.Invoice.needs_review == False,  # noqa: E712
                models.Invoice.workspace_id == ws_id,
            )
        )
    ).scalar_one()

    # Document status counts
    failed_docs = (
        await session.execute(
            select(func.count(models.Document.id)).where(
                models.Document.status == "failed", models.Document.workspace_id == ws_id
            )
        )
    ).scalar_one()
    processing_docs = (
        await session.execute(
            select(func.count(models.Document.id)).where(
                models.Document.status == "processing", models.Document.workspace_id == ws_id
            )
        )
    ).scalar_one()
    complete_docs = (
        await session.execute(
            select(func.count(models.Document.id)).where(
                models.Document.status == "complete", models.Document.workspace_id == ws_id
            )
        )
    ).scalar_one()

    # Batch counts
    batch_count = (
        await session.execute(
            select(func.count(models.Batch.id)).where(models.Batch.workspace_id == ws_id)
        )
    ).scalar_one()

    # Storage usage
    storage_usage = (
        await session.execute(
            select(func.sum(models.Document.file_size_bytes)).where(
                models.Document.workspace_id == ws_id
            )
        )
    ).scalar_one() or 0

    # Recent uploads (last 10)
    recent_result = await session.execute(
        select(models.Document)
        .where(models.Document.workspace_id == ws_id)
        .order_by(models.Document.created_at.desc())
        .limit(10)
    )
    recent_docs = recent_result.scalars().all()

    # Top 10 vendors by invoice count
    vendor_stats_result = await session.execute(
        select(
            models.Vendor.canonical_name,
            func.count(models.Invoice.id).label("invoice_count"),
        )
        .join(models.Invoice, models.Invoice.vendor_id == models.Vendor.id)
        .where(models.Invoice.workspace_id == ws_id)
        .group_by(models.Vendor.canonical_name)
        .order_by(func.count(models.Invoice.id).desc())
        .limit(10)
    )
    vendor_stats = vendor_stats_result.all()

    return {
        "totals": {
            "invoices": total_invoices,
            "needs_review": needs_review,
            "approved": approved,
            "failed_documents": failed_docs,
            "processing_documents": processing_docs,
            "complete_documents": complete_docs,
            "batches": batch_count,
            "storage_usage_bytes": storage_usage,
        },
        "provider_preference": workspace.provider_preference,
        "recent_uploads": [
            {
                "document_id": d.id,
                "filename": d.filename,
                "status": d.status,
                "batch_id": d.batch_id,
                "created_at": d.created_at.isoformat(),
            }
            for d in recent_docs
        ],
        "vendor_statistics": [
            {"vendor_name": name, "invoice_count": count}
            for name, count in vendor_stats
        ],
    }


@router.get("/search")
async def search_invoices(
    q: str | None = Query(default=None, description="Free-text search"),
    vendor: str | None = Query(default=None),
    invoice_number: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    batch_id: str | None = Query(default=None),
    status: str | None = Query(default=None, description="needs_review | approved | failed"),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """
    Search invoices by vendor, invoice number, date, batch, status, or confidence.
    """
    from sqlalchemy.orm import selectinload

    stmt = (
        select(models.Invoice)
        .options(
            selectinload(models.Invoice.vendor),
            selectinload(models.Invoice.document),
        )
        .join(models.Document, models.Invoice.document_id == models.Document.id)
        .outerjoin(models.Vendor, models.Invoice.vendor_id == models.Vendor.id)
        .where(models.Invoice.workspace_id == workspace.id)
    )

    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                models.Invoice.invoice_number.ilike(like),
                models.Vendor.canonical_name.ilike(like),
                models.Document.filename.ilike(like),
            )
        )
    if vendor:
        stmt = stmt.where(models.Vendor.canonical_name.ilike(f"%{vendor}%"))
    if invoice_number:
        stmt = stmt.where(models.Invoice.invoice_number.ilike(f"%{invoice_number}%"))
    if start_date:
        stmt = stmt.where(models.Invoice.invoice_date >= start_date)
    if end_date:
        stmt = stmt.where(models.Invoice.invoice_date <= end_date)
    if batch_id:
        stmt = stmt.where(models.Document.batch_id == batch_id)
    if status == "needs_review":
        stmt = stmt.where(models.Invoice.needs_review == True)  # noqa: E712
    elif status == "approved":
        stmt = stmt.where(models.Invoice.needs_review == False)  # noqa: E712
    elif status == "failed":
        stmt = stmt.where(models.Document.status == "failed")
    if min_confidence is not None:
        stmt = stmt.where(
            models.Invoice.confidence_breakdown["overall_score"].as_float() >= min_confidence
        )

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = stmt.order_by(models.Invoice.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    invoices = result.scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "vendor_name": inv.vendor.canonical_name if inv.vendor else None,
                "invoice_date": inv.invoice_date,
                "total_amount": str(inv.total_amount) if inv.total_amount else None,
                "currency": inv.currency,
                "needs_review": inv.needs_review,
                "document_status": inv.document.status if inv.document else None,
                "batch_id": inv.document.batch_id if inv.document else None,
                "filename": inv.document.filename if inv.document else None,
            }
            for inv in invoices
        ],
    }
