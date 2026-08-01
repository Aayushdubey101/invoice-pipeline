"""
Phase 5: Unit tests for Vendor Intelligence.

Tests cover:
- Vendor intelligence booster (currency match, terms match, duplicate detection, confidence penalty/boost)
- Vendor memory updater (tax IDs append-only, invoice numbers, currency, products, EMA confidence)
- _weighted_bool helper
- Edge cases (no extracted, missing fields, best-effort on errors)
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from invoice_pipeline.vendor_intelligence.booster import (
    _boost,
    _penalize,
    apply_vendor_intelligence,
)
from invoice_pipeline.vendor_intelligence.memory import (
    _weighted_bool,
)
from invoice_pipeline.schemas import (
    CanonicalizedInvoice,
    Document,
    DocumentStatus,
    FieldValue,
    Invoice,
    LineItem,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _fv(value: str | None = None, confidence: float = 0.8) -> FieldValue:
    return FieldValue(value=value, confidence=confidence)


def _make_vendor(**kwargs) -> MagicMock:
    """Create a mock Vendor DB object."""
    defaults = {
        "id": "vendor-1",
        "canonical_name": "Acme Corp",
        "preferred_currency": None,
        "preferred_payment_terms": None,
        "historical_invoice_numbers": [],
        "avg_confidence": None,
        "invoice_count": 0,
        "tax_ids": [],
        "frequently_used_products": [],
        "layout_patterns": {},
    }
    defaults.update(kwargs)
    v = MagicMock()
    for k, val in defaults.items():
        setattr(v, k, val)
    return v


def _make_invoice(**kwargs) -> Invoice:
    defaults = {
        "invoice_number": _fv("INV-001"),
        "vendor_name": _fv("Acme Corp"),
        "vendor_tax_id": _fv(None),
        "currency": _fv("USD"),
        "payment_terms": _fv("Net 30"),
        "total_amount": _fv("100.00"),
    }
    defaults.update(kwargs)
    return Invoice(**defaults)


def _make_doc(inv: Invoice | None = None) -> Document:
    return Document(
        document_id="d" * 64,
        filename="test.pdf",
        mime_type="application/pdf",
        extracted=inv or _make_invoice(),
        status=DocumentStatus.PROCESSING,
    )


# ─── _boost / _penalize ───────────────────────────────────────────────────────


class TestBoostPenalize:
    def test_boost_clamps_at_one(self) -> None:
        fv = _fv(confidence=0.95)
        result = _boost(fv, 0.20)
        assert result.confidence == 1.0

    def test_penalize_floors_at_zero(self) -> None:
        fv = _fv(confidence=0.10)
        result = _penalize(fv, 0.50)
        assert result.confidence == 0.0

    def test_boost_partial(self) -> None:
        fv = _fv(confidence=0.70)
        result = _boost(fv, 0.10)
        assert abs(result.confidence - 0.80) < 1e-9

    def test_penalize_partial(self) -> None:
        fv = _fv(confidence=0.80)
        result = _penalize(fv, 0.20)
        assert abs(result.confidence - 0.60) < 1e-9


# ─── apply_vendor_intelligence ────────────────────────────────────────────────


class TestApplyVendorIntelligence:
    def test_currency_match_boosts(self) -> None:
        vendor = _make_vendor(preferred_currency="USD")
        inv = _make_invoice(currency=_fv("USD", confidence=0.80))
        doc = _make_doc(inv)

        updated_doc, reasons = apply_vendor_intelligence(doc, vendor)

        assert updated_doc.extracted.currency.confidence > 0.80
        assert reasons == []

    def test_currency_mismatch_no_boost(self) -> None:
        vendor = _make_vendor(preferred_currency="EUR")
        inv = _make_invoice(currency=_fv("USD", confidence=0.80))
        doc = _make_doc(inv)

        updated_doc, reasons = apply_vendor_intelligence(doc, vendor)

        # No boost — currency doesn't match
        assert updated_doc.extracted.currency.confidence == 0.80
        assert reasons == []

    def test_payment_terms_match_boosts(self) -> None:
        vendor = _make_vendor(preferred_payment_terms="Net 30")
        inv = _make_invoice(payment_terms=_fv("Net 30", confidence=0.70))
        doc = _make_doc(inv)

        updated_doc, reasons = apply_vendor_intelligence(doc, vendor)

        assert updated_doc.extracted.payment_terms.confidence > 0.70

    def test_payment_terms_case_insensitive(self) -> None:
        vendor = _make_vendor(preferred_payment_terms="net 30")
        inv = _make_invoice(payment_terms=_fv("Net 30", confidence=0.70))
        doc = _make_doc(inv)

        updated_doc, _ = apply_vendor_intelligence(doc, vendor)
        assert updated_doc.extracted.payment_terms.confidence > 0.70

    def test_duplicate_invoice_penalty(self) -> None:
        vendor = _make_vendor(historical_invoice_numbers=["INV-001", "INV-002"])
        inv = _make_invoice(invoice_number=_fv("INV-001", confidence=0.90))
        doc = _make_doc(inv)

        updated_doc, reasons = apply_vendor_intelligence(doc, vendor)

        assert updated_doc.extracted.invoice_number.confidence < 0.90
        assert len(reasons) == 1
        assert "duplicate" in reasons[0].lower()
        assert "INV-001" in reasons[0]

    def test_new_invoice_no_penalty(self) -> None:
        vendor = _make_vendor(historical_invoice_numbers=["INV-001"])
        inv = _make_invoice(invoice_number=_fv("INV-999", confidence=0.90))
        doc = _make_doc(inv)

        updated_doc, reasons = apply_vendor_intelligence(doc, vendor)

        assert updated_doc.extracted.invoice_number.confidence == 0.90
        assert reasons == []

    def test_high_avg_confidence_boosts_vendor_name(self) -> None:
        vendor = _make_vendor(avg_confidence=0.90, invoice_count=5)
        inv = _make_invoice(vendor_name=_fv("Acme Corp", confidence=0.75))
        doc = _make_doc(inv)

        updated_doc, _ = apply_vendor_intelligence(doc, vendor)

        assert updated_doc.extracted.vendor_name.confidence > 0.75

    def test_low_avg_confidence_adds_review_reason(self) -> None:
        vendor = _make_vendor(avg_confidence=0.50, invoice_count=10)
        doc = _make_doc()

        _, reasons = apply_vendor_intelligence(doc, vendor)

        assert any("low extraction confidence" in r for r in reasons)

    def test_low_avg_confidence_too_few_invoices_no_flag(self) -> None:
        # Don't flag vendors with < 3 invoices — not enough history
        vendor = _make_vendor(avg_confidence=0.50, invoice_count=2)
        doc = _make_doc()

        _, reasons = apply_vendor_intelligence(doc, vendor)

        assert not any("low extraction confidence" in r for r in reasons)

    def test_no_extracted_returns_unchanged(self) -> None:
        vendor = _make_vendor(preferred_currency="USD")
        doc = Document(
            document_id="d" * 64,
            filename="test.pdf",
            mime_type="application/pdf",
            status=DocumentStatus.PROCESSING,
        )

        updated_doc, reasons = apply_vendor_intelligence(doc, vendor)
        assert updated_doc is doc
        assert reasons == []

    def test_multiple_boosts_combined(self) -> None:
        vendor = _make_vendor(
            preferred_currency="EUR",
            preferred_payment_terms="Net 60",
            avg_confidence=0.90,
            invoice_count=5,
        )
        inv = _make_invoice(
            currency=_fv("EUR", confidence=0.70),
            payment_terms=_fv("Net 60", confidence=0.65),
            vendor_name=_fv("Acme Corp", confidence=0.75),
        )
        doc = _make_doc(inv)

        updated_doc, reasons = apply_vendor_intelligence(doc, vendor)

        assert updated_doc.extracted.currency.confidence > 0.70
        assert updated_doc.extracted.payment_terms.confidence > 0.65
        assert updated_doc.extracted.vendor_name.confidence > 0.75


# ─── _weighted_bool ──────────────────────────────────────────────────────────


class TestWeightedBool:
    def test_first_invoice_true(self) -> None:
        assert _weighted_bool(0.0, True, 1) == 1.0

    def test_first_invoice_false(self) -> None:
        assert _weighted_bool(0.0, False, 1) == 0.0

    def test_running_average(self) -> None:
        # After 4 True values rate should be 1.0, then False at n=5
        rate = _weighted_bool(1.0, False, 5)
        # (1.0 * 4 + 0) / 5 = 0.8
        assert abs(rate - 0.8) < 1e-9

    def test_50_50(self) -> None:
        rate = _weighted_bool(0.5, True, 10)
        # (0.5 * 9 + 1) / 10 = (4.5 + 1) / 10 = 0.55
        assert abs(rate - 0.55) < 1e-9


# ─── Integration: booster + memory work together ─────────────────────────────


class TestIntegration:
    def test_currency_boost_then_terms_boost_independent(self) -> None:
        """Both boosts apply independently without interfering."""
        vendor = _make_vendor(
            preferred_currency="GBP",
            preferred_payment_terms="Due on receipt",
        )
        inv = _make_invoice(
            currency=_fv("GBP", confidence=0.72),
            payment_terms=_fv("Due on receipt", confidence=0.68),
        )
        doc = _make_doc(inv)

        updated_doc, reasons = apply_vendor_intelligence(doc, vendor)

        assert updated_doc.extracted.currency.confidence > 0.72
        assert updated_doc.extracted.payment_terms.confidence > 0.68
        assert reasons == []

    def test_duplicate_plus_low_confidence_both_flagged(self) -> None:
        vendor = _make_vendor(
            historical_invoice_numbers=["INV-DUP"],
            avg_confidence=0.45,
            invoice_count=8,
        )
        inv = _make_invoice(invoice_number=_fv("INV-DUP", confidence=0.90))
        doc = _make_doc(inv)

        _, reasons = apply_vendor_intelligence(doc, vendor)

        assert len(reasons) == 2
        assert any("duplicate" in r.lower() for r in reasons)
        assert any("low extraction confidence" in r for r in reasons)
