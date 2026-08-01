from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from invoice_pipeline.api.deps import get_current_workspace
from invoice_pipeline.api.metrics import REVIEW_ACTIONS_TOTAL
from invoice_pipeline.db import models
from invoice_pipeline.db.models import Workspace
from invoice_pipeline.db.session import get_session

log = structlog.get_logger()
router = APIRouter()


class FieldUpdateBody(BaseModel):
    reviewed_value: str | None
    correction_reason: str | None = None


def _queue_item(inv: models.Invoice) -> dict[str, Any]:
    return {
        "id": inv.id,
        "document_id": inv.document_id,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date,
        "vendor_id": inv.vendor_id,
        "vendor_name": inv.vendor.canonical_name if inv.vendor else None,
        "buyer_name": inv.buyer_name,
        "total_amount": str(inv.total_amount) if inv.total_amount else None,
        "currency": inv.currency,
        "needs_review": inv.needs_review,
        "review_reasons": inv.review_reasons,
        "document_status": inv.document.status,
        "filename": inv.document.filename,
        "created_at": inv.document.created_at.isoformat(),
    }


@router.get("/queue")
async def review_queue(
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    result = await session.execute(
        select(models.Invoice)
        .where(
            models.Invoice.needs_review == True,  # noqa: E712
            models.Invoice.workspace_id == workspace.id,
        )
        .options(
            selectinload(models.Invoice.vendor),
            selectinload(models.Invoice.document),
        )
        .order_by(models.Invoice.created_at.desc())
        .limit(100)
    )
    invoices = result.scalars().all()
    return {"items": [_queue_item(inv) for inv in invoices], "total": len(invoices)}


@router.post("/{invoice_id}/approve")
async def approve_invoice(
    invoice_id: str,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    result = await session.execute(
        select(models.Invoice)
        .where(models.Invoice.id == invoice_id, models.Invoice.workspace_id == workspace.id)
        .options(
            selectinload(models.Invoice.fields),
            selectinload(models.Invoice.document),
        )
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    inv.needs_review = False
    for field in inv.fields:
        if not field.reviewed:
            field.reviewed = True

    inv.document.status = "complete"

    session.add(
        models.AuditLog(
            document_id=inv.document_id,
            workspace_id=inv.workspace_id,
            actor="user",
            stage="review",
            action="approved",
            extra={"invoice_id": invoice_id},
        )
    )
    await session.commit()
    REVIEW_ACTIONS_TOTAL.labels(action="approved").inc()
    return {"invoice_id": invoice_id, "status": "approved"}


@router.post("/{invoice_id}/reject")
async def reject_invoice(
    invoice_id: str,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    result = await session.execute(
        select(models.Invoice)
        .where(models.Invoice.id == invoice_id, models.Invoice.workspace_id == workspace.id)
        .options(selectinload(models.Invoice.document))
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    inv.document.status = "failed"
    inv.needs_review = False

    session.add(
        models.AuditLog(
            document_id=inv.document_id,
            workspace_id=inv.workspace_id,
            actor="user",
            stage="review",
            action="rejected",
            extra={"invoice_id": invoice_id},
        )
    )
    await session.commit()
    REVIEW_ACTIONS_TOTAL.labels(action="rejected").inc()
    return {"invoice_id": invoice_id, "status": "rejected"}


@router.patch("/{invoice_id}/field/{field_id}")
async def update_field(
    invoice_id: str,
    field_id: str,
    body: FieldUpdateBody,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    result = await session.execute(
        select(models.InvoiceField)
        .join(models.Invoice, models.InvoiceField.invoice_id == models.Invoice.id)
        .where(
            models.InvoiceField.id == field_id,
            models.InvoiceField.invoice_id == invoice_id,
            models.Invoice.workspace_id == workspace.id,
        )
        .options(
            selectinload(models.InvoiceField.invoice).selectinload(models.Invoice.document),
            selectinload(models.InvoiceField.invoice).selectinload(models.Invoice.vendor)
        )
    )
    field = result.scalar_one_or_none()
    if field is None:
        raise HTTPException(status_code=404, detail="Field not found")

    # If the value is actually changed, record feedback learning dataset
    original_val = field.canonical_value or field.raw_value
    if body.reviewed_value != original_val:
        feedback = models.ReviewerFeedback(
            workspace_id=field.invoice.workspace_id,
            document_id=field.invoice.document_id,
            vendor_id=field.invoice.vendor_id,
            field_type=field.field_name,
            invoice_type=field.invoice.document.doc_type,
            original_value=original_val,
            corrected_value=body.reviewed_value,
            confidence=field.confidence,
            correction_reason=body.correction_reason
        )
        session.add(feedback)

    field.reviewed_value = body.reviewed_value
    field.reviewed = True

    session.add(
        models.AuditLog(
            document_id=field.invoice.document_id,
            workspace_id=field.invoice.workspace_id,
            actor="user",
            stage="review",
            action="field_corrected",
            extra={
                "field_id": field_id,
                "field_name": field.field_name,
                "reviewed_value": body.reviewed_value,
                "correction_reason": body.correction_reason
            },
        )
    )
    await session.commit()
    return {"field_id": field_id, "reviewed_value": body.reviewed_value}
