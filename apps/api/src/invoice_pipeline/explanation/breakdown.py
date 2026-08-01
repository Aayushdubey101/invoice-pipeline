"""
Phase 6: Explainable Extraction — Confidence Breakdown Builder.

Produces a structured, human-readable explanation for every field's
confidence score: what the LLM said, which heuristics fired, whether
the value was grounded in the source text, and what the final score is.

Design principles:
- Pure functions; no I/O, no side effects.
- All monetary/Decimal comparisons delegate to existing canonicalizers.
- The breakdown dict is stored verbatim in `invoices.confidence_breakdown`
  (JSONB) so the review UI can render it without re-running logic.
- Every FieldExplanation records a `signals` list — ordered log of score
  adjustments — so reviewers can see exactly how the score moved.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from invoice_pipeline.canonicalizers.currency import parse_amount
from invoice_pipeline.schemas import CanonicalizedInvoice, FieldValue, Invoice

# ─── ISO-4217 set (kept local; mirrors confidence_score.py for consistency) ──

_ISO_4217 = {
    "USD", "EUR", "GBP", "JPY", "CNY", "INR", "AUD", "CAD", "CHF",
    "HKD", "SGD", "SEK", "NOK", "DKK", "MXN", "BRL", "RUB", "ZAR",
    "NZD", "AED", "THB", "IDR", "PLN", "CZK", "HUF", "ILS", "CLP",
    "PKR", "PHP", "MYR",
}

_GROUNDING_CAP = 0.50


# ─── Models ──────────────────────────────────────────────────────────────────


class Signal(BaseModel):
    """A single score adjustment event."""

    label: str          # Short human-readable name  e.g. "date_parseable"
    description: str    # Full sentence e.g. "Invoice date '2024-03-14' is parseable (+0.10)"
    delta: float        # Signed score change (positive = boost, negative = penalty)
    category: str       # "heuristic" | "grounding" | "vendor_intelligence" | "llm_base"


class FieldExplanation(BaseModel):
    """Full explanation for one invoice field."""

    field_name: str
    llm_value: str | None           # Raw LLM output
    llm_confidence: float           # Score directly from the LLM
    final_confidence: float         # After all signals applied
    grounded: bool | None           # None if no raw text available
    signals: list[Signal] = Field(default_factory=list)
    summary: str = ""               # One-sentence human summary


class ConfidenceBreakdown(BaseModel):
    """Complete explainability report for an invoice extraction run."""

    fields: dict[str, FieldExplanation] = Field(default_factory=dict)
    math_check: bool | None = None      # subtotal + tax ≈ total
    math_delta: float = 0.0            # score delta applied to financial fields
    grounding_applied: bool = False     # was grounding capping applied to any field
    vendor_intelligence_applied: bool = False
    overall_score: float = 0.0         # simple mean of final confidences for key fields
    summary: str = ""

    def model_dump_summary(self) -> dict[str, Any]:
        """Return a compact JSON-safe dict for DB storage."""
        return self.model_dump(mode="json")


# ─── Builder ─────────────────────────────────────────────────────────────────

_KEY_FIELDS = (
    "invoice_number",
    "invoice_date",
    "due_date",
    "vendor_name",
    "buyer_name",
    "subtotal",
    "tax_amount",
    "total_amount",
    "currency",
    "payment_terms",
    "purchase_order",
    "vendor_tax_id",
    "vendor_address",
    "buyer_address",
)


def build_confidence_breakdown(
    *,
    original_invoice: Invoice,
    scored_invoice: Invoice,
    raw_text: str,
    canonicalized: CanonicalizedInvoice | None,
    vendor_matched: bool,
    vendor_intelligence_applied: bool = False,
) -> ConfidenceBreakdown:
    """
    Compute a ConfidenceBreakdown by comparing the original LLM extraction
    with the post-heuristic scored invoice.

    Parameters
    ----------
    original_invoice:
        Invoice as returned by the LLM (before any heuristics).
    scored_invoice:
        Invoice after _apply_heuristics + _apply_grounding.
    raw_text:
        Full OCR/text content for grounding checks.
    canonicalized:
        The canonicalized invoice (used for math check reporting).
    vendor_matched:
        Whether the vendor was found in the DB.
    vendor_intelligence_applied:
        Whether Phase-5 booster touched any field.
    """
    math_result = _math_checks_out(original_invoice)
    haystack = "".join(raw_text.split()).casefold() if raw_text else ""

    field_explanations: dict[str, FieldExplanation] = {}

    for field_name in _KEY_FIELDS:
        orig_fv: FieldValue = getattr(original_invoice, field_name)
        final_fv: FieldValue = getattr(scored_invoice, field_name)

        signals: list[Signal] = [
            Signal(
                label="llm_base",
                description=(
                    f"LLM reported '{orig_fv.value}' with confidence {orig_fv.confidence:.2f}."
                ),
                delta=0.0,
                category="llm_base",
            )
        ]

        net_delta = final_fv.confidence - orig_fv.confidence

        # ── Date heuristic ───────────────────────────────────────────────────
        if field_name in ("invoice_date", "due_date") and orig_fv.value:
            if _is_parseable_date(orig_fv.value):
                signals.append(Signal(
                    label="date_parseable",
                    description=f"'{orig_fv.value}' is a valid parseable date (+0.10).",
                    delta=0.10,
                    category="heuristic",
                ))

        # ── Currency heuristic ───────────────────────────────────────────────
        if field_name == "currency" and orig_fv.value:
            if _is_known_currency(orig_fv.value):
                signals.append(Signal(
                    label="known_iso4217_currency",
                    description=f"'{orig_fv.value}' is a recognised ISO-4217 currency code (+0.10).",
                    delta=0.10,
                    category="heuristic",
                ))

        # ── Math heuristic ───────────────────────────────────────────────────
        if field_name in ("subtotal", "tax_amount", "total_amount"):
            if math_result is True:
                signals.append(Signal(
                    label="math_subtotal_plus_tax_equals_total",
                    description="subtotal + tax_amount ≈ total_amount (within 1% tolerance) (+0.20).",
                    delta=0.20,
                    category="heuristic",
                ))
            elif math_result is False:
                signals.append(Signal(
                    label="math_contradiction",
                    description=(
                        "subtotal + tax_amount ≠ total_amount — at least one amount is wrong. "
                        f"Confidence capped at {_GROUNDING_CAP}."
                    ),
                    delta=min(0.0, _GROUNDING_CAP - orig_fv.confidence),
                    category="heuristic",
                ))

        # ── Vendor match heuristic ───────────────────────────────────────────
        if field_name == "vendor_name" and vendor_matched:
            signals.append(Signal(
                label="vendor_matched",
                description="Vendor matched an existing canonical record (+0.10).",
                delta=0.10,
                category="heuristic",
            ))

        # ── Grounding check ──────────────────────────────────────────────────
        grounded: bool | None = None
        if haystack and orig_fv.value:
            needle = "".join(orig_fv.value.split()).casefold()
            grounded = bool(needle and needle in haystack)
            if not grounded and orig_fv.confidence > _GROUNDING_CAP:
                signals.append(Signal(
                    label="not_grounded_in_source",
                    description=(
                        f"Value '{orig_fv.value}' was not found in the source text — "
                        f"possible hallucination. Confidence capped at {_GROUNDING_CAP}."
                    ),
                    delta=min(0.0, _GROUNDING_CAP - orig_fv.confidence),
                    category="grounding",
                ))
            elif grounded:
                signals.append(Signal(
                    label="grounded_in_source",
                    description=f"Value '{orig_fv.value}' was found verbatim in the source text.",
                    delta=0.0,
                    category="grounding",
                ))

        # ── Vendor intelligence boost/penalty (Phase 5) ──────────────────────
        if vendor_intelligence_applied and abs(net_delta) > 1e-6:
            # The exact delta is already captured in net_delta; only report
            # if no other signal explains the gap
            signals_delta = sum(s.delta for s in signals[1:])  # skip llm_base
            unexplained = net_delta - signals_delta
            if abs(unexplained) > 0.01:
                signals.append(Signal(
                    label="vendor_intelligence",
                    description=(
                        f"Vendor history {'boosted' if unexplained > 0 else 'penalised'} "
                        f"this field by {unexplained:+.2f}."
                    ),
                    delta=round(unexplained, 4),
                    category="vendor_intelligence",
                ))

        # ── Build summary ────────────────────────────────────────────────────
        reasons = [s.label for s in signals[1:] if s.label not in ("grounded_in_source",)]
        if not reasons:
            field_summary = f"Score unchanged at {final_fv.confidence:.2f}."
        elif final_fv.confidence >= 0.85:
            field_summary = f"High confidence ({final_fv.confidence:.2f}). Signals: {', '.join(reasons)}."
        elif final_fv.confidence >= 0.65:
            field_summary = f"Moderate confidence ({final_fv.confidence:.2f}). Signals: {', '.join(reasons)}."
        else:
            field_summary = f"Low confidence ({final_fv.confidence:.2f}) — review required. Signals: {', '.join(reasons)}."

        field_explanations[field_name] = FieldExplanation(
            field_name=field_name,
            llm_value=orig_fv.value,
            llm_confidence=round(orig_fv.confidence, 4),
            final_confidence=round(final_fv.confidence, 4),
            grounded=grounded,
            signals=signals,
            summary=field_summary,
        )

    # ── Overall score (mean of key financial + identity fields) ──────────────
    _score_fields = ("invoice_number", "invoice_date", "vendor_name", "total_amount", "currency")
    scores = [field_explanations[f].final_confidence for f in _score_fields if f in field_explanations]
    overall = round(sum(scores) / len(scores), 4) if scores else 0.0

    grounding_applied = any(
        any(s.label == "not_grounded_in_source" for s in fe.signals)
        for fe in field_explanations.values()
    )

    # ── Overall summary sentence ─────────────────────────────────────────────
    if overall >= 0.85:
        overall_summary = f"Extraction quality is high (overall {overall:.0%})."
    elif overall >= 0.65:
        overall_summary = (
            f"Extraction quality is moderate (overall {overall:.0%}). "
            "Some fields may require review."
        )
    else:
        overall_summary = (
            f"Extraction quality is low (overall {overall:.0%}). "
            "Human review is strongly recommended."
        )

    if math_result is False:
        overall_summary += " ⚠ Financial totals do not add up."
    if grounding_applied:
        overall_summary += " ⚠ Some values could not be grounded in the source document."

    return ConfidenceBreakdown(
        fields=field_explanations,
        math_check=math_result,
        math_delta=0.20 if math_result is True else (round(_GROUNDING_CAP - 0.8, 2) if math_result is False else 0.0),
        grounding_applied=grounding_applied,
        vendor_intelligence_applied=vendor_intelligence_applied,
        overall_score=overall,
        summary=overall_summary,
    )


# ─── Private helpers ─────────────────────────────────────────────────────────


def _is_parseable_date(value: str) -> bool:
    try:
        import dateparser
        return dateparser.parse(value) is not None
    except Exception:
        return False


def _is_known_currency(value: str) -> bool:
    return value.strip().upper() in _ISO_4217


def _math_checks_out(invoice: Invoice) -> bool | None:
    subtotal = parse_amount(invoice.subtotal.value)
    tax = parse_amount(invoice.tax_amount.value)
    total = parse_amount(invoice.total_amount.value)
    if subtotal is None or tax is None or total is None or total == 0:
        return None
    tolerance = abs(total) * Decimal("0.01")
    return abs(subtotal + tax - total) <= tolerance
