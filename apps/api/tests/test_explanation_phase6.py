"""Tests for Phase 6: Explainable Extraction (Confidence Breakdown)."""

import pytest
from decimal import Decimal

from invoice_pipeline.explanation.breakdown import build_confidence_breakdown
from invoice_pipeline.schemas import CanonicalizedInvoice, FieldValue, Invoice


def make_invoice(**kwargs) -> Invoice:
    """Helper to build a dummy invoice with defaults."""
    default = FieldValue(value="test", confidence=0.5, evidence="")
    data = {
        "invoice_number": default,
        "invoice_date": default,
        "due_date": default,
        "vendor_name": default,
        "vendor_address": default,
        "vendor_tax_id": default,
        "buyer_name": default,
        "buyer_address": default,
        "subtotal": default,
        "tax_amount": default,
        "total_amount": default,
        "currency": default,
        "payment_terms": default,
        "purchase_order": default,
        "line_items": [],
    }
    data.update(kwargs)
    return Invoice(**data)


def test_breakdown_grounding_penalty():
    """Test that missing grounding caps score and emits correct signal."""
    # LLM says "Apple" but OCR is "Banana Corp"
    original = make_invoice(vendor_name=FieldValue(value="Apple", confidence=0.9, evidence=""))
    # The grounding heuristic caps it at 0.5
    scored = make_invoice(vendor_name=FieldValue(value="Apple", confidence=0.5, evidence=""))
    
    breakdown = build_confidence_breakdown(
        original_invoice=original,
        scored_invoice=scored,
        raw_text="Banana Corp Invoice #123",
        canonicalized=None,
        vendor_matched=False
    )
    
    fe = breakdown.fields["vendor_name"]
    assert fe.field_name == "vendor_name"
    assert fe.llm_confidence == 0.9
    assert fe.final_confidence == 0.5
    assert fe.grounded is False
    
    # Check signals: llm_base, then not_grounded_in_source
    sig_labels = [s.label for s in fe.signals]
    assert "llm_base" in sig_labels
    assert "not_grounded_in_source" in sig_labels
    
    pen_sig = next(s for s in fe.signals if s.label == "not_grounded_in_source")
    assert pen_sig.delta == -0.4  # capped from 0.9 to 0.5


def test_breakdown_grounding_ok():
    """Test that present grounding emits success signal without penalty."""
    original = make_invoice(vendor_name=FieldValue(value="Banana Corp", confidence=0.9, evidence=""))
    scored = make_invoice(vendor_name=FieldValue(value="Banana Corp", confidence=0.9, evidence=""))
    
    breakdown = build_confidence_breakdown(
        original_invoice=original,
        scored_invoice=scored,
        raw_text="Banana Corp Invoice #123",
        canonicalized=None,
        vendor_matched=False
    )
    
    fe = breakdown.fields["vendor_name"]
    assert fe.grounded is True
    sig_labels = [s.label for s in fe.signals]
    assert "grounded_in_source" in sig_labels


def test_breakdown_math_check():
    """Test that valid math adds a boost signal."""
    original = make_invoice(
        subtotal=FieldValue(value="100.00", confidence=0.6, evidence=""),
        tax_amount=FieldValue(value="20.00", confidence=0.6, evidence=""),
        total_amount=FieldValue(value="120.00", confidence=0.6, evidence=""),
    )
    scored = make_invoice(
        subtotal=FieldValue(value="100.00", confidence=0.8, evidence=""),
        tax_amount=FieldValue(value="20.00", confidence=0.8, evidence=""),
        total_amount=FieldValue(value="120.00", confidence=0.8, evidence=""),
    )
    
    breakdown = build_confidence_breakdown(
        original_invoice=original,
        scored_invoice=scored,
        raw_text="100.00 20.00 120.00",
        canonicalized=None,
        vendor_matched=False
    )
    
    assert breakdown.math_check is True
    fe = breakdown.fields["total_amount"]
    assert any(s.label == "math_subtotal_plus_tax_equals_total" for s in fe.signals)


def test_breakdown_vendor_intelligence():
    """Test that vendor intelligence emits a signal if there's an unexplained delta."""
    # LLM gave 0.6, no heuristics applied (except date maybe, but we check vendor_name)
    # final is 0.85 -> 0.25 jump unexplained
    original = make_invoice(vendor_name=FieldValue(value="Apple", confidence=0.6, evidence=""))
    scored = make_invoice(vendor_name=FieldValue(value="Apple", confidence=0.85, evidence=""))
    
    breakdown = build_confidence_breakdown(
        original_invoice=original,
        scored_invoice=scored,
        raw_text="Apple Inc",
        canonicalized=None,
        vendor_matched=False,
        vendor_intelligence_applied=True
    )
    
    fe = breakdown.fields["vendor_name"]
    vi_sig = next(s for s in fe.signals if s.label == "vendor_intelligence")
    assert abs(vi_sig.delta - 0.25) < 0.001
    assert "boosted" in vi_sig.description
