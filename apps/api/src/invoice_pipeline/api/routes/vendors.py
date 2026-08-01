from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.api.deps import get_current_workspace
from invoice_pipeline.db import models
from invoice_pipeline.db.models import Workspace
from invoice_pipeline.db.session import get_session

router = APIRouter()


class VendorUpdateBody(BaseModel):
    canonical_name: str | None = None
    aliases: list[str] | None = None
    status: str | None = None


def _vendor_row(v: models.Vendor) -> dict[str, Any]:
    return {
        "id": v.id,
        "canonical_name": v.canonical_name,
        "aliases": v.aliases,
        "address": v.address,
        "tax_id": v.tax_id,
        "status": v.status,
        "created_at": v.created_at.isoformat(),
        # Phase 5: Vendor Intelligence Memory
        "tax_ids": v.tax_ids or [],
        "historical_invoice_numbers": v.historical_invoice_numbers or [],
        "preferred_currency": v.preferred_currency,
        "preferred_payment_terms": v.preferred_payment_terms,
        "frequently_used_products": v.frequently_used_products or [],
        "avg_confidence": float(v.avg_confidence) if v.avg_confidence is not None else None,
        "invoice_count": v.invoice_count or 0,
        "layout_patterns": v.layout_patterns or {},
    }


@router.get("/")
async def list_vendors(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    total = (
        await session.execute(
            select(func.count())
            .select_from(models.Vendor)
            .where(models.Vendor.workspace_id == workspace.id)
        )
    ).scalar_one()
    result = await session.execute(
        select(models.Vendor)
        .where(models.Vendor.workspace_id == workspace.id)
        .order_by(models.Vendor.canonical_name)
        .offset(skip)
        .limit(limit)
    )
    vendors = result.scalars().all()
    return {"items": [_vendor_row(v) for v in vendors], "total": total}


@router.patch("/{vendor_id}")
async def update_vendor(
    vendor_id: str,
    body: VendorUpdateBody,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    vendor = await session.get(models.Vendor, vendor_id)
    if vendor is None or vendor.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Vendor not found")

    if body.canonical_name is not None:
        vendor.canonical_name = body.canonical_name
    if body.aliases is not None:
        vendor.aliases = body.aliases
    if body.status is not None:
        vendor.status = body.status

    await session.commit()
    return _vendor_row(vendor)
