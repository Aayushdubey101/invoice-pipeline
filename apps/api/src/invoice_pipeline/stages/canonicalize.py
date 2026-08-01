import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.canonicalizers.currency import normalize_currency, parse_amount
from invoice_pipeline.canonicalizers.dates import parse_date
from invoice_pipeline.canonicalizers.tax_ids import validate_tax_id
from invoice_pipeline.canonicalizers.vendors import match_or_create_vendor
from invoice_pipeline.db import models
from invoice_pipeline.schemas import CanonicalizedInvoice, Document, PipelineError
from invoice_pipeline.vendor_intelligence.booster import apply_vendor_intelligence

log = structlog.get_logger()


async def canonicalize(doc: Document, session: AsyncSession) -> Document:
    if doc.extracted is None:
        return doc
    try:
        inv = doc.extracted

        invoice_date = parse_date(inv.invoice_date.value)
        due_date = parse_date(inv.due_date.value)
        currency = normalize_currency(inv.currency.value)
        subtotal = parse_amount(inv.subtotal.value)
        tax_amount = parse_amount(inv.tax_amount.value)
        total_amount = parse_amount(inv.total_amount.value)
        _vendor_tax_id = validate_tax_id(inv.vendor_tax_id.value)

        vendor_id = None
        vendor_matched = False
        intelligence_reasons: list[str] = []
        if inv.vendor_name.value:
            vendor_id, vendor_matched = await match_or_create_vendor(
                inv.vendor_name.value, session, doc.workspace_id
            )

        # Phase 5: Apply vendor intelligence boosts if we matched a known vendor
        if vendor_id and vendor_matched:
            vendor_row = await session.get(models.Vendor, vendor_id)
            if vendor_row is not None:
                doc, intelligence_reasons = apply_vendor_intelligence(doc, vendor_row)
                # Reload inv after potential modifications
                inv = doc.extracted  # type: ignore[assignment]

        canon = CanonicalizedInvoice(
            invoice_number=inv.invoice_number.value,
            invoice_date=invoice_date,
            due_date=due_date,
            vendor_id=vendor_id,
            buyer_name=inv.buyer_name.value,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            currency=currency,
            payment_terms=inv.payment_terms.value,
            purchase_order=inv.purchase_order.value,
            raw=inv,
        )

        if intelligence_reasons:
            canon = canon.model_copy(
                update={
                    "needs_review": True,
                    "review_reasons": list(canon.review_reasons) + intelligence_reasons,
                }
            )

        log.info(
            "pipeline_stage",
            stage="canonicalize",
            document_id=doc.document_id,
            vendor_matched=vendor_matched,
            vendor_id=str(vendor_id) if vendor_id else None,
            currency=currency,
            total_amount=str(total_amount) if total_amount else None,
        )
        return doc.model_copy(update={"canonicalized": canon, "vendor_matched": vendor_matched})
    except Exception as exc:
        log.error(
            "pipeline_stage_error",
            stage="canonicalize",
            document_id=doc.document_id,
            error=str(exc),
        )
        error = PipelineError(stage="canonicalize", message=str(exc))
        return doc.model_copy(update={"errors": [*doc.errors, error]})
