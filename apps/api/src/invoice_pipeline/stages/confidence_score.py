"""
Confidence scoring stage.
Heuristics applied per spec:
  +0.1 date parseable
  +0.1 currency known
  +0.2 math checks out (subtotal + tax ≈ total)
  +0.1 vendor matched
  cap at 1.0; flag < LOW_CONFIDENCE_THRESHOLD as needs_review
"""

from decimal import Decimal, InvalidOperation

import structlog

from invoice_pipeline.config import settings
from invoice_pipeline.schemas import (
    CanonicalizedInvoice,
    Document,
    FieldValue,
    Invoice,
    PipelineError,
)

log = structlog.get_logger()

_ISO_4217 = {
    "USD", "EUR", "GBP", "JPY", "CNY", "INR", "AUD", "CAD", "CHF", "HKD",
    "SGD", "SEK", "NOK", "DKK", "MXN", "BRL", "RUB", "ZAR", "NZD", "AED",
    "THB", "IDR", "PLN", "CZK", "HUF", "ILS", "CLP", "PKR", "PHP", "MYR",
}


async def score_confidence(doc: Document) -> Document:
    if doc.extracted is None:
        return doc
    try:
        scored = _apply_heuristics(doc.extracted, vendor_matched=doc.vendor_matched)
        needs_review, reasons = _check_review(scored)

        canon = doc.canonicalized or CanonicalizedInvoice(raw=scored)
        canon = canon.model_copy(update={"needs_review": needs_review, "review_reasons": reasons})

        log.info(
            "pipeline_stage",
            stage="confidence_score",
            document_id=doc.document_id,
            needs_review=needs_review,
            reasons=reasons,
        )
        return doc.model_copy(update={"extracted": scored, "canonicalized": canon})
    except Exception as exc:
        log.error("pipeline_stage_error", stage="confidence_score", document_id=doc.document_id, error=str(exc))
        error = PipelineError(stage="confidence_score", message=str(exc))
        return doc.model_copy(update={"errors": [*doc.errors, error]})


def _apply_heuristics(invoice: Invoice, vendor_matched: bool = False) -> Invoice:
    updates: dict = {}

    def _boost(fv: FieldValue, delta: float) -> FieldValue:
        return fv.model_copy(update={"confidence": min(1.0, fv.confidence + delta)})

    for date_field in ("invoice_date", "due_date"):
        fv: FieldValue = getattr(invoice, date_field)
        if fv.value and _is_parseable_date(fv.value):
            updates[date_field] = _boost(fv, 0.1)

    currency_fv = invoice.currency
    if currency_fv.value and _is_known_currency(currency_fv.value):
        updates["currency"] = _boost(currency_fv, 0.1)

    if _math_checks_out(invoice):
        for amt_field in ("subtotal", "tax_amount", "total_amount"):
            fv = getattr(invoice, amt_field)
            updated_fv = updates.get(amt_field, fv)
            updates[amt_field] = _boost(updated_fv, 0.2)

    if vendor_matched:
        fv = invoice.vendor_name
        updates["vendor_name"] = _boost(updates.get("vendor_name", fv), 0.1)

    return invoice.model_copy(update=updates)


def _check_review(invoice: Invoice) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    threshold = settings.LOW_CONFIDENCE_THRESHOLD

    fields_to_check = (
        "invoice_number", "invoice_date", "vendor_name",
        "total_amount", "currency",
    )
    for field_name in fields_to_check:
        fv: FieldValue = getattr(invoice, field_name)
        if fv.confidence < threshold:
            reasons.append(f"{field_name}: confidence {fv.confidence:.2f} < {threshold}")

    return bool(reasons), reasons


def _is_parseable_date(value: str) -> bool:
    try:
        import dateparser
        result = dateparser.parse(value)
        return result is not None
    except Exception:
        return False


def _is_known_currency(value: str) -> bool:
    return value.strip().upper() in _ISO_4217


def _math_checks_out(invoice: Invoice) -> bool:
    try:
        subtotal = Decimal(invoice.subtotal.value or "0")
        tax = Decimal(invoice.tax_amount.value or "0")
        total = Decimal(invoice.total_amount.value or "0")
        if total == 0:
            return False
        expected = subtotal + tax
        tolerance = total * Decimal("0.01")
        return abs(expected - total) <= tolerance
    except (InvalidOperation, TypeError):
        return False
