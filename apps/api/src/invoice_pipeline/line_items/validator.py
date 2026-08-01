"""
Phase 4 — Advanced Line Item Extraction: Math Validator

Validates that per-row arithmetic is consistent (qty × unit_price ≈ total).
Marks rows as math_valid=True/False/None (None = insufficient data to validate).
Flags rows with mismatches in the review reasons.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

import structlog

from invoice_pipeline.schemas import RichLineItem

log = structlog.get_logger()

_TOLERANCE = Decimal("0.05")  # 5 cents / 5% — absorbs rounding artifacts


def _parse_decimal(raw: str | None) -> Decimal | None:
    """Parse a raw string amount into Decimal. Returns None on failure."""
    if raw is None:
        return None
    # Strip currency symbols, whitespace, thousands separators
    cleaned = re.sub(r"[^\d.,\-]", "", raw).strip()
    if not cleaned:
        return None
    # Handle European comma-decimal: "1.234,56" → "1234.56"
    if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        # 1,234.56 style — remove commas
        cleaned = cleaned.replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def validate_line_item_math(items: list[RichLineItem]) -> list[RichLineItem]:
    """
    Validate each RichLineItem's arithmetic.

    For ITEM rows only: if qty and unit_price and total are all parseable,
    check that qty * unit_price ≈ total (within _TOLERANCE).
    Sets math_valid accordingly. Other row types are left as-is.

    Returns the updated list with math_valid populated.
    """
    validated: list[RichLineItem] = []
    for item in items:
        if item.row_type.value not in ("item", "unknown"):
            # Non-item rows (discount, tax, subtotal, total, shipping) — skip math check
            validated.append(item)
            continue

        qty = _parse_decimal(item.quantity.value)
        up = _parse_decimal(item.unit_price.value)
        total = _parse_decimal(item.total.value)

        if qty is None or up is None or total is None:
            # Insufficient data — can't validate
            validated.append(item.model_copy(update={"math_valid": None}))
            continue

        expected = qty * up
        diff = abs(expected - abs(total))  # abs(total) handles negative rows

        if diff <= _TOLERANCE or (expected != 0 and diff / abs(expected) < Decimal("0.01")):
            math_valid = True
        else:
            math_valid = False
            log.warning(
                "line_item_math_mismatch",
                qty=str(qty),
                unit_price=str(up),
                total=str(total),
                expected=str(expected),
                diff=str(diff),
            )

        validated.append(item.model_copy(update={"math_valid": math_valid}))

    return validated


def collect_math_errors(items: list[RichLineItem]) -> list[str]:
    """Return human-readable strings for each math-invalid row."""
    errors: list[str] = []
    for idx, item in enumerate(items):
        if item.math_valid is False:
            desc = item.description.value or f"Row {idx + 1}"
            qty_str = item.quantity.value or "?"
            up_str = item.unit_price.value or "?"
            total_str = item.total.value or "?"
            errors.append(
                f"Line {idx + 1} math mismatch: "
                f"{desc!r} qty={qty_str} × price={up_str} ≠ total={total_str}"
            )
    return errors
