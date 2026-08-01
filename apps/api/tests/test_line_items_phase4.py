"""
Phase 4: Unit tests for Advanced Line Item Extraction.

Tests cover:
- Math validation (valid, invalid, missing data, European formats)
- Row type classification (all 7 types + default ITEM)
- Extractor orchestration (legacy promotion, rich path)
- Edge cases (empty list, all None values, special row types skip math)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from invoice_pipeline.line_items.classifier import classify_line_items, classify_row_type
from invoice_pipeline.line_items.extractor import extract_rich_line_items, _field_to_cell
from invoice_pipeline.line_items.validator import (
    _parse_decimal,
    collect_math_errors,
    validate_line_item_math,
)
from invoice_pipeline.schemas import (
    CellValue,
    Document,
    DocumentStatus,
    DocumentType,
    FieldValue,
    Invoice,
    LineItem,
    RichLineItem,
    RowType,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_cell(value: str | None, confidence: float = 1.0) -> CellValue:
    return CellValue(value=value, confidence=confidence)


def _make_rich(
    desc: str | None = None,
    qty: str | None = None,
    up: str | None = None,
    total: str | None = None,
    row_type: RowType = RowType.ITEM,
) -> RichLineItem:
    return RichLineItem(
        description=_make_cell(desc),
        quantity=_make_cell(qty),
        unit_price=_make_cell(up),
        total=_make_cell(total),
        row_type=row_type,
    )


def _make_invoice_doc(line_items: list[LineItem] | None = None) -> Document:
    """Create a minimal Document with an extracted Invoice."""
    inv = Invoice(line_items=line_items or [])
    return Document(
        document_id="deadbeef" * 8,
        filename="test.pdf",
        mime_type="application/pdf",
        extracted=inv,
        status=DocumentStatus.PROCESSING,
    )


# ─── _parse_decimal ───────────────────────────────────────────────────────────


class TestParseDecimal:
    def test_simple_integer(self) -> None:
        assert _parse_decimal("100") == Decimal("100")

    def test_simple_decimal(self) -> None:
        assert _parse_decimal("12.50") == Decimal("12.50")

    def test_dollar_sign_stripped(self) -> None:
        assert _parse_decimal("$1,234.56") == Decimal("1234.56")

    def test_euro_european_format(self) -> None:
        # "1.234,56" → 1234.56
        result = _parse_decimal("1.234,56")
        assert result == Decimal("1234.56")

    def test_comma_decimal_only(self) -> None:
        # "75,50" → 75.50
        assert _parse_decimal("75,50") == Decimal("75.50")

    def test_none_input(self) -> None:
        assert _parse_decimal(None) is None

    def test_empty_string(self) -> None:
        assert _parse_decimal("") is None

    def test_non_numeric(self) -> None:
        assert _parse_decimal("N/A") is None

    def test_negative(self) -> None:
        assert _parse_decimal("-50.00") == Decimal("-50.00")

    def test_european_space_separator(self) -> None:
        # "75 974,00" — strip spaces
        assert _parse_decimal("75 974,00") == Decimal("75974.00")


# ─── validate_line_item_math ──────────────────────────────────────────────────


class TestValidateLineItemMath:
    def test_valid_math(self) -> None:
        items = [_make_rich(qty="2", up="50.00", total="100.00")]
        result = validate_line_item_math(items)
        assert result[0].math_valid is True

    def test_invalid_math(self) -> None:
        items = [_make_rich(qty="2", up="50.00", total="90.00")]
        result = validate_line_item_math(items)
        assert result[0].math_valid is False

    def test_within_tolerance(self) -> None:
        # diff = 0.04 < 0.05 tolerance
        items = [_make_rich(qty="3", up="33.33", total="100.00")]
        result = validate_line_item_math(items)
        assert result[0].math_valid is True

    def test_none_qty_skips(self) -> None:
        items = [_make_rich(qty=None, up="50.00", total="100.00")]
        result = validate_line_item_math(items)
        assert result[0].math_valid is None

    def test_none_all_skips(self) -> None:
        items = [_make_rich()]
        result = validate_line_item_math(items)
        assert result[0].math_valid is None

    def test_subtotal_row_skipped(self) -> None:
        # Non-item rows skip math validation
        items = [_make_rich(qty="10", up="5", total="999", row_type=RowType.SUBTOTAL)]
        result = validate_line_item_math(items)
        # math_valid not set to False — row was not validated
        assert result[0].math_valid is None

    def test_tax_row_skipped(self) -> None:
        items = [_make_rich(qty="1", up="20", total="999", row_type=RowType.TAX)]
        result = validate_line_item_math(items)
        assert result[0].math_valid is None

    def test_empty_list(self) -> None:
        assert validate_line_item_math([]) == []

    def test_european_format(self) -> None:
        items = [_make_rich(qty="3", up="1.234,00", total="3.702,00")]
        result = validate_line_item_math(items)
        assert result[0].math_valid is True


class TestCollectMathErrors:
    def test_no_errors(self) -> None:
        items = [_make_rich(qty="2", up="50", total="100")]
        validated = validate_line_item_math(items)
        assert collect_math_errors(validated) == []

    def test_one_error(self) -> None:
        items = [_make_rich(desc="Widget", qty="2", up="50.00", total="90.00")]
        validated = validate_line_item_math(items)
        errors = collect_math_errors(validated)
        assert len(errors) == 1
        assert "Widget" in errors[0]
        assert "math mismatch" in errors[0]

    def test_skipped_rows_not_flagged(self) -> None:
        items = [_make_rich(qty="1", up="20", total="999", row_type=RowType.TAX)]
        validated = validate_line_item_math(items)
        assert collect_math_errors(validated) == []


# ─── classify_row_type ────────────────────────────────────────────────────────


class TestClassifyRowType:
    @pytest.mark.parametrize(
        "description,expected",
        [
            ("Widget A", RowType.ITEM),
            ("Discount 10%", RowType.DISCOUNT),
            ("Remise spéciale", RowType.DISCOUNT),
            ("TVA 20%", RowType.TAX),
            ("VAT 5%", RowType.TAX),
            ("Subtotal", RowType.SUBTOTAL),
            ("Total HT", RowType.SUBTOTAL),
            ("Grand Total", RowType.TOTAL),
            ("Total Due", RowType.TOTAL),
            ("Shipping", RowType.SHIPPING),
            ("Frais de port", RowType.SHIPPING),
            ("Continued from page 1", RowType.HEADER),
            (None, RowType.UNKNOWN),
            ("", RowType.UNKNOWN),
        ],
    )
    def test_classify(self, description: str | None, expected: RowType) -> None:
        assert classify_row_type(description) == expected


class TestClassifyLineItems:
    def test_preserves_explicit_type(self) -> None:
        # If LLM set tax explicitly, don't override
        items = [_make_rich(desc="Some fee", row_type=RowType.TAX)]
        result = classify_line_items(items)
        assert result[0].row_type == RowType.TAX

    def test_classifies_default_item(self) -> None:
        items = [_make_rich(desc="Shipping fee")]
        result = classify_line_items(items)
        assert result[0].row_type == RowType.SHIPPING

    def test_unknown_becomes_item(self) -> None:
        items = [_make_rich(desc="Custom widget", row_type=RowType.UNKNOWN)]
        result = classify_line_items(items)
        assert result[0].row_type == RowType.ITEM

    def test_empty_list(self) -> None:
        assert classify_line_items([]) == []


# ─── _field_to_cell ───────────────────────────────────────────────────────────


class TestFieldToCell:
    def test_basic_conversion(self) -> None:
        fv = FieldValue(value="100.00", confidence=0.9, evidence="Total: 100.00")
        cell = _field_to_cell(fv, page=2)
        assert cell.value == "100.00"
        assert cell.confidence == 0.9
        assert cell.evidence == "Total: 100.00"
        assert cell.page == 2
        assert cell.bbox is None

    def test_none_page(self) -> None:
        fv = FieldValue(value=None)
        cell = _field_to_cell(fv)
        assert cell.page is None


# ─── extract_rich_line_items ──────────────────────────────────────────────────


class TestExtractRichLineItems:
    def test_no_extracted_returns_empty(self) -> None:
        doc = Document(
            document_id="a" * 64,
            filename="test.pdf",
            mime_type="application/pdf",
        )
        items, errors = extract_rich_line_items(doc)
        assert items == []
        assert errors == []

    def test_promotes_legacy_items(self) -> None:
        legacy = [
            LineItem(
                description=FieldValue(value="Widget", confidence=0.9),
                quantity=FieldValue(value="2"),
                unit_price=FieldValue(value="50.00"),
                total=FieldValue(value="100.00"),
            )
        ]
        doc = _make_invoice_doc(line_items=legacy)
        items, errors = extract_rich_line_items(doc)
        assert len(items) == 1
        assert items[0].description.value == "Widget"
        assert items[0].math_valid is True  # 2 * 50 = 100

    def test_math_errors_returned(self) -> None:
        legacy = [
            LineItem(
                description=FieldValue(value="Widget"),
                quantity=FieldValue(value="2"),
                unit_price=FieldValue(value="50.00"),
                total=FieldValue(value="90.00"),  # wrong!
            )
        ]
        doc = _make_invoice_doc(line_items=legacy)
        items, errors = extract_rich_line_items(doc)
        assert len(errors) == 1
        assert "math mismatch" in errors[0]

    def test_empty_line_items(self) -> None:
        doc = _make_invoice_doc(line_items=[])
        items, errors = extract_rich_line_items(doc)
        assert items == []
        assert errors == []

    def test_row_types_classified(self) -> None:
        legacy = [
            LineItem(
                description=FieldValue(value="Subtotal"),
                quantity=FieldValue(value=None),
                unit_price=FieldValue(value=None),
                total=FieldValue(value="500.00"),
            ),
            LineItem(
                description=FieldValue(value="VAT 20%"),
                quantity=FieldValue(value=None),
                unit_price=FieldValue(value=None),
                total=FieldValue(value="100.00"),
            ),
        ]
        doc = _make_invoice_doc(line_items=legacy)
        items, errors = extract_rich_line_items(doc)
        assert items[0].row_type == RowType.SUBTOTAL
        assert items[1].row_type == RowType.TAX
        # No math errors — these rows are skipped
        assert errors == []
