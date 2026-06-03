from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from invoice_pipeline.db.session import get_session
from invoice_pipeline.db import models

router = APIRouter()


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(models.Invoice)
        .where(models.Invoice.id == invoice_id)
        .options(
            selectinload(models.Invoice.fields),
            selectinload(models.Invoice.line_items),
            selectinload(models.Invoice.vendor),
            selectinload(models.Invoice.document),
        )
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return {
        "id": inv.id,
        "document_id": inv.document_id,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date,
        "vendor_id": inv.vendor_id,
        "vendor_name": inv.vendor.canonical_name if inv.vendor else None,
        "buyer_name": inv.buyer_name,
        "subtotal": str(inv.subtotal) if inv.subtotal else None,
        "tax_amount": str(inv.tax_amount) if inv.tax_amount else None,
        "total_amount": str(inv.total_amount) if inv.total_amount else None,
        "currency": inv.currency,
        "payment_terms": inv.payment_terms,
        "purchase_order": inv.purchase_order,
        "needs_review": inv.needs_review,
        "review_reasons": inv.review_reasons,
        "filename": inv.document.filename,
        "document_status": inv.document.status,
        "fields": [
            {
                "id": f.id,
                "field_name": f.field_name,
                "raw_value": f.raw_value,
                "canonical_value": f.canonical_value,
                "confidence": float(f.confidence),
                "evidence": f.evidence,
                "needs_review": f.needs_review,
                "reviewed": f.reviewed,
                "reviewed_value": f.reviewed_value,
            }
            for f in inv.fields
        ],
        "line_items": [
            {
                "id": li.id,
                "position": li.position,
                "description": li.description_raw,
                "quantity": li.quantity_raw,
                "unit_price": li.unit_price_raw,
                "total": li.total_raw,
            }
            for li in sorted(inv.line_items, key=lambda x: x.position)
        ],
        "raw_extraction": inv.raw_extraction,
    }
