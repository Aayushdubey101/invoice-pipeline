"""
Confidence scoring stage.
Heuristics applied per spec:
  +0.1 date parseable
  +0.1 currency known
  +0.2 math checks out (subtotal + tax ≈ total)
  +0.1 vendor matched
  cap at 1.0; flag < LOW_CONFIDENCE_THRESHOLD as needs_review
"""

from decimal import Decimal

import structlog

from invoice_pipeline.canonicalizers.currency import parse_amount
from invoice_pipeline.config import settings
from invoice_pipeline.explanation.breakdown import build_confidence_breakdown
from invoice_pipeline.schemas import (
    CanonicalizedInvoice,
    Document,
    FieldValue,
    Invoice,
    Page,
    PipelineError,
)

log = structlog.get_logger()

_ISO_4217 = {
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CNY",
    "INR",
    "AUD",
    "CAD",
    "CHF",
    "HKD",
    "SGD",
    "SEK",
    "NOK",
    "DKK",
    "MXN",
    "BRL",
    "RUB",
    "ZAR",
    "NZD",
    "AED",
    "THB",
    "IDR",
    "PLN",
    "CZK",
    "HUF",
    "ILS",
    "CLP",
    "PKR",
    "PHP",
    "MYR",
}


async def score_confidence(doc: Document) -> Document:
    if doc.extracted is None:
        return doc
    try:
        # Phase 6: keep original (pre-heuristic) for explanation diff
        original_invoice = doc.extracted

        scored = _apply_heuristics(doc.extracted, vendor_matched=doc.vendor_matched)
        scored = apply_grounding(scored, doc.pages, doc.raw_text)
        needs_review, reasons = _check_review(scored)

        canon = doc.canonicalized or CanonicalizedInvoice(raw=scored)
        canon = canon.model_copy(update={"needs_review": needs_review, "review_reasons": reasons})

        # Phase 6: Build structured confidence breakdown
        breakdown = build_confidence_breakdown(
            original_invoice=original_invoice,
            scored_invoice=scored,
            raw_text=doc.raw_text,
            canonicalized=canon,
            vendor_matched=doc.vendor_matched,
            vendor_intelligence_applied=(
                doc.canonicalized is not None
                and bool(doc.canonicalized.vendor_id)
            ),
        )

        log.info(
            "pipeline_stage",
            stage="confidence_score",
            document_id=doc.document_id,
            needs_review=needs_review,
            reasons=reasons,
            overall_score=breakdown.overall_score,
        )
        return doc.model_copy(update={
            "extracted": scored,
            "canonicalized": canon,
            "confidence_breakdown": breakdown.model_dump_summary(),
        })
    except Exception as exc:
        log.error(
            "pipeline_stage_error",
            stage="confidence_score",
            document_id=doc.document_id,
            error=str(exc),
        )
        error = PipelineError(stage="confidence_score", message=str(exc))
        return doc.model_copy(update={"errors": [*doc.errors, error]})


def _apply_heuristics(invoice: Invoice, vendor_matched: bool = False) -> Invoice:
    updates: dict[str, FieldValue] = {}

    def _boost(fv: FieldValue, delta: float) -> FieldValue:
        return fv.model_copy(update={"confidence": min(1.0, fv.confidence + delta)})

    for date_field in ("invoice_date", "due_date"):
        fv: FieldValue = getattr(invoice, date_field)
        if fv.value and _is_parseable_date(fv.value):
            updates[date_field] = _boost(fv, 0.1)

    currency_fv = invoice.currency
    if currency_fv.value and _is_known_currency(currency_fv.value):
        updates["currency"] = _boost(currency_fv, 0.1)

    math_ok = _math_checks_out(invoice)
    for amt_field in ("subtotal", "tax_amount", "total_amount"):
        fv = updates.get(amt_field, getattr(invoice, amt_field))
        if math_ok:
            updates[amt_field] = _boost(fv, 0.2)
        elif math_ok is False and fv.confidence > _GROUNDING_CAP:
            # amounts contradict each other → at least one is wrong; force review
            updates[amt_field] = fv.model_copy(update={"confidence": _GROUNDING_CAP})

    if vendor_matched:
        fv = invoice.vendor_name
        updates["vendor_name"] = _boost(updates.get("vendor_name", fv), 0.1)

    return invoice.model_copy(update=updates)


_GROUNDING_CAP = 0.5  # ungrounded value → forced below review threshold


def apply_grounding(invoice: Invoice, pages: list[Page], raw_text: str) -> Invoice:
    """Cap confidence of any field whose value doesn't appear in the OCR text.
    Also computes spatial bounding box (page, bbox) for UI jump-to-source.
    """
    if not raw_text:
        return invoice

    haystack = "".join(raw_text.split()).casefold()
    updates: dict[str, FieldValue] = {}
    
    for name, fv in invoice:
        if not isinstance(fv, FieldValue) or not fv.value:
            continue
            
        needle = "".join(fv.value.split()).casefold()
        update_dict = {}
        
        # 1. Check if grounded in text
        if needle and needle not in haystack and fv.confidence > _GROUNDING_CAP:
            update_dict["confidence"] = _GROUNDING_CAP
            
        # 2. Compute spatial bbox if we have word data
        if needle and pages:
            # simple sliding window over words per page
            found = False
            for page in pages:
                if found: break
                if not page.words: continue
                
                # We do a fast check if needle might be on this page
                page_haystack = "".join(w.text for w in page.words).casefold()
                if needle not in page_haystack:
                    continue
                    
                for i in range(len(page.words)):
                    if found: break
                    for j in range(i + 1, min(i + 15, len(page.words) + 1)):
                        chunk = "".join(w.text for w in page.words[i:j]).casefold()
                        if needle in chunk:
                            bboxes = [w.bbox for w in page.words[i:j] if w.bbox]
                            if bboxes:
                                x0 = min(b[0] for b in bboxes)
                                y0 = min(b[1] for b in bboxes)
                                x1 = max(b[2] for b in bboxes)
                                y1 = max(b[3] for b in bboxes)
                                update_dict["page"] = page.page_num
                                update_dict["bbox"] = [x0, y0, x1, y1]
                                found = True
                            break
                            
        if update_dict:
            updates[name] = fv.model_copy(update=update_dict)

    return invoice.model_copy(update=updates) if updates else invoice


async def ground_fields(doc: Document) -> Document:
    """Pipeline stage: computes field-level bbox + caps confidence of ungrounded
    (hallucinated) values, feeding both jump-to-source and the llm confidence
    signal. Runs standalone (not via score_confidence, which is superseded by
    ConfidenceEngine) so it stays additive to the live scoring path.
    """
    if doc.extracted is None:
        return doc
    try:
        grounded = apply_grounding(doc.extracted, doc.pages, doc.raw_text)
        return doc.model_copy(update={"extracted": grounded})
    except Exception as exc:
        log.error(
            "pipeline_stage_error",
            stage="ground_fields",
            document_id=doc.document_id,
            error=str(exc),
        )
        error = PipelineError(stage="ground_fields", message=str(exc))
        return doc.model_copy(update={"errors": [*doc.errors, error]})


def _check_review(invoice: Invoice) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    threshold = settings.LOW_CONFIDENCE_THRESHOLD

    fields_to_check = (
        "invoice_number",
        "invoice_date",
        "vendor_name",
        "total_amount",
        "currency",
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


def _math_checks_out(invoice: Invoice) -> bool | None:
    """True = subtotal + tax ≈ total. False = contradiction. None = can't evaluate.

    Uses parse_amount so EU formats ("75 974,00", "€82 003,30") work — plain
    Decimal() raised on them, silently disabling this check for EU invoices.
    """
    subtotal = parse_amount(invoice.subtotal.value)
    tax = parse_amount(invoice.tax_amount.value)
    total = parse_amount(invoice.total_amount.value)
    if subtotal is None or tax is None or total is None or total == 0:
        return None
    tolerance = abs(total) * Decimal("0.01")
    return abs(subtotal + tax - total) <= tolerance
