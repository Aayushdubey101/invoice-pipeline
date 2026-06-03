from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.db.session import get_session
from invoice_pipeline.db import models

router = APIRouter()


class VendorUpdateBody(BaseModel):
    canonical_name: str | None = None
    aliases: list[str] | None = None
    status: str | None = None


def _vendor_row(v: models.Vendor) -> dict:
    return {
        "id": v.id,
        "canonical_name": v.canonical_name,
        "aliases": v.aliases,
        "address": v.address,
        "tax_id": v.tax_id,
        "status": v.status,
        "created_at": v.created_at.isoformat(),
    }


@router.get("/")
async def list_vendors(session: AsyncSession = Depends(get_session)) -> dict:
    result = await session.execute(select(models.Vendor).order_by(models.Vendor.canonical_name))
    vendors = result.scalars().all()
    return {"items": [_vendor_row(v) for v in vendors], "total": len(vendors)}


@router.patch("/{vendor_id}")
async def update_vendor(
    vendor_id: str,
    body: VendorUpdateBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    vendor = await session.get(models.Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")

    if body.canonical_name is not None:
        vendor.canonical_name = body.canonical_name
    if body.aliases is not None:
        vendor.aliases = body.aliases
    if body.status is not None:
        vendor.status = body.status

    await session.commit()
    return _vendor_row(vendor)
