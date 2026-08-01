import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from invoice_pipeline.db import models
from invoice_pipeline.schemas import Document, CanonicalizedInvoice

log = structlog.get_logger()

async def learn_vendor_template(doc: Document, session: AsyncSession) -> None:
    """
    Learns the vendor template from a canonicalized invoice.
    Extracts bounding boxes and relative positions for fields and stores them in a template.
    """
    if not doc.canonicalized or not doc.canonicalized.vendor_id:
        return

    # If it needs review, don't learn from it yet! We only want to learn from confident docs.
    # But wait, phase 10 introduces reviewer feedback learning. For now, let's learn if it doesn't need review.
    if doc.canonicalized.needs_review:
        return

    vendor_id = doc.canonicalized.vendor_id
    raw_inv = doc.canonicalized.raw

    # Check if a template already exists, for now we will just create a new version if it doesn't exist
    stmt = (
        select(models.VendorTemplate)
        .where(
            models.VendorTemplate.vendor_id == vendor_id,
            models.VendorTemplate.workspace_id == doc.workspace_id,
        )
        .order_by(models.VendorTemplate.version.desc())
    )
    result = await session.execute(stmt)
    latest_template = result.scalars().first()

    version = 1
    if latest_template:
        # For this naive implementation, we'll only create a template if one doesn't exist.
        # A more advanced implementation would merge/update templates.
        return

    # Create a fingerprint from the vendor name and perhaps address
    fingerprint = raw_inv.vendor_name.value if raw_inv.vendor_name.value else "Unknown Vendor"

    template = models.VendorTemplate(
        vendor_id=vendor_id,
        workspace_id=doc.workspace_id,
        version=version,
        fingerprint=fingerprint,
        header_positions={},
        invoice_number_location=raw_inv.invoice_number.bbox if raw_inv.invoice_number.bbox else {},
        date_location=raw_inv.invoice_date.bbox if raw_inv.invoice_date.bbox else {},
        table_structure={"line_items_count": len(raw_inv.line_items) if raw_inv.line_items else 0},
        logo_location={},
        footer_pattern={},
        ocr_corrections={}
    )

    session.add(template)
    await session.flush()
    log.info("vendor_template_learned", vendor_id=vendor_id, version=version)
