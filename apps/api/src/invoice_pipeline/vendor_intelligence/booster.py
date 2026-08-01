"""
Phase 5 — Vendor Intelligence: Extraction Confidence Booster

Uses stored vendor memory to improve the confidence of extracted fields
BEFORE the main confidence engine runs. This lets known-good vendor patterns
raise low-confidence extractions without needing the LLM to re-run.

Boosts applied:
  - currency matches preferred_currency          → +0.10 on currency field
  - payment_terms matches preferred_payment_terms → +0.08 on payment_terms field
  - invoice_number not in historical set          → no change (first-time is normal)
  - invoice_number IS in historical set           → -0.20 (possible duplicate)
  - vendor has high avg_confidence (≥0.85)        → +0.05 on vendor_name field
  - vendor has low avg_confidence (<0.60)         → adds review reason

All boosts are capped at 1.0. Penalties are floored at 0.0.
"""

from __future__ import annotations

import structlog

from invoice_pipeline.db.models import Vendor
from invoice_pipeline.schemas import Document, FieldValue, Invoice, PipelineError

log = structlog.get_logger()

_CURRENCY_MATCH_BOOST = 0.10
_TERMS_MATCH_BOOST = 0.08
_VENDOR_HIGH_CONFIDENCE_BOOST = 0.05
_DUPLICATE_PENALTY = 0.20
_VENDOR_HIGH_CONFIDENCE_THRESHOLD = 0.85
_VENDOR_LOW_CONFIDENCE_THRESHOLD = 0.60


def _boost(fv: FieldValue, delta: float) -> FieldValue:
    return fv.model_copy(update={"confidence": min(1.0, fv.confidence + delta)})


def _penalize(fv: FieldValue, delta: float) -> FieldValue:
    return fv.model_copy(update={"confidence": max(0.0, fv.confidence - delta)})


def apply_vendor_intelligence(
    doc: Document,
    vendor: Vendor,
) -> tuple[Document, list[str]]:
    """
    Apply vendor memory boosts/penalties to the extracted invoice.

    Returns (updated_doc, extra_review_reasons).
    Best-effort: if any error occurs, original doc is returned unchanged.
    """
    review_reasons: list[str] = []

    try:
        if doc.extracted is None:
            return doc, []

        inv: Invoice = doc.extracted
        updates: dict[str, FieldValue] = {}

        # ── Currency match boost ──────────────────────────────────────────────
        if vendor.preferred_currency and inv.currency.value:
            if inv.currency.value.upper() == vendor.preferred_currency.upper():
                updates["currency"] = _boost(inv.currency, _CURRENCY_MATCH_BOOST)
                log.debug(
                    "vendor_intelligence_currency_boost",
                    vendor_id=vendor.id,
                    currency=inv.currency.value,
                )

        # ── Payment terms match boost ─────────────────────────────────────────
        if vendor.preferred_payment_terms and inv.payment_terms.value:
            # Fuzzy compare: normalise whitespace + case
            def _norm(s: str) -> str:
                return " ".join(s.strip().lower().split())

            if _norm(inv.payment_terms.value) == _norm(vendor.preferred_payment_terms):
                updates["payment_terms"] = _boost(inv.payment_terms, _TERMS_MATCH_BOOST)

        # ── Duplicate invoice number penalty ─────────────────────────────────
        inv_num = inv.invoice_number.value
        historical = vendor.historical_invoice_numbers or []
        if inv_num and inv_num in historical:
            updates["invoice_number"] = _penalize(inv.invoice_number, _DUPLICATE_PENALTY)
            review_reasons.append(
                f"Invoice number {inv_num!r} seen before for vendor {vendor.canonical_name!r} — possible duplicate"
            )
            log.warning(
                "vendor_intelligence_duplicate_invoice",
                vendor_id=vendor.id,
                invoice_number=inv_num,
            )

        # ── Vendor confidence boost from historical average ───────────────────
        if vendor.avg_confidence is not None:
            avg = float(vendor.avg_confidence)
            if avg >= _VENDOR_HIGH_CONFIDENCE_THRESHOLD:
                updates["vendor_name"] = _boost(inv.vendor_name, _VENDOR_HIGH_CONFIDENCE_BOOST)
            elif avg < _VENDOR_LOW_CONFIDENCE_THRESHOLD and vendor.invoice_count and vendor.invoice_count >= 3:
                # Established vendor with consistently low confidence — flag for review
                review_reasons.append(
                    f"Vendor {vendor.canonical_name!r} has historically low extraction confidence "
                    f"({avg:.2f}) — manual verification recommended"
                )

        if updates:
            updated_inv = inv.model_copy(update=updates)
            doc = doc.model_copy(update={"extracted": updated_inv})

        return doc, review_reasons

    except Exception as exc:
        log.error(
            "vendor_intelligence_boost_failed",
            vendor_id=vendor.id,
            error=str(exc),
        )
        return doc, []
