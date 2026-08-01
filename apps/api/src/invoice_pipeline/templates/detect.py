import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from invoice_pipeline.db import models
from invoice_pipeline.schemas import Document
from invoice_pipeline.canonicalizers.vendors import match_or_create_vendor

log = structlog.get_logger()

async def apply_vendor_templates(doc: Document, session: AsyncSession) -> Document:
    """
    Attempts to identify the vendor from raw text before full LLM extraction.
    If a template is found, attaches it to the document (e.g. injects hints into raw_text).
    """
    if not doc.raw_text.strip():
        return doc

    # We do a naive search in raw text for known vendor fingerprints
    stmt = select(models.VendorTemplate).where(
        models.VendorTemplate.is_active == True,
        models.VendorTemplate.workspace_id == doc.workspace_id,
    )
    result = await session.execute(stmt)
    templates = result.scalars().all()

    best_template = None
    for tmpl in templates:
        if tmpl.fingerprint and tmpl.fingerprint.lower() in doc.raw_text.lower():
            best_template = tmpl
            break

    if best_template:
        log.info("vendor_template_applied", template_id=best_template.id, vendor_id=best_template.vendor_id)
        # Inject hints into raw_text or store them for field_extract
        # For simplicity, we prepend the hints to the raw text
        hints = [f"--- VENDOR TEMPLATE DETECTED: {best_template.fingerprint} ---"]
        if best_template.invoice_number_location:
            hints.append(f"Hint: Invoice Number is typically located around bbox {best_template.invoice_number_location}")
        if best_template.date_location:
            hints.append(f"Hint: Date is typically located around bbox {best_template.date_location}")
        
        doc = doc.model_copy(update={"raw_text": "\n".join(hints) + "\n\n" + doc.raw_text})

    return doc
