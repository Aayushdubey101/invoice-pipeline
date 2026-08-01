"""
Phase 4 — Advanced Line Item Extraction: Row Classifier

Classifies each line item row as ITEM / DISCOUNT / TAX / SUBTOTAL / TOTAL /
SHIPPING / HEADER based on heuristic keyword matching on the description cell.
"""

from __future__ import annotations

import re

from invoice_pipeline.schemas import RichLineItem, RowType

# ─── Keyword patterns for each row type ───────────────────────────────────────

_PATTERNS: list[tuple[RowType, re.Pattern[str]]] = [
    # Check more specific types first
    (
        RowType.TOTAL,
        re.compile(
            r"\b(grand\s+total|total\s+due|total\s+amount|montant\s+total|"
            r"total\s+ttc|gesamt(betrag)?|total\s+a\s+pagar)\b",
            re.IGNORECASE,
        ),
    ),
    (
        RowType.SUBTOTAL,
        re.compile(
            r"\b(sub\s*total|total\s+ht|net\s+amount|zwischensumme|"
            r"montant\s+ht|before\s+tax)\b",
            re.IGNORECASE,
        ),
    ),
    (
        RowType.TAX,
        re.compile(
            r"\b(tax|tva|vat|mwst|iva|gst|hst|sales\s+tax|taxe|impuesto)\b",
            re.IGNORECASE,
        ),
    ),
    (
        RowType.DISCOUNT,
        re.compile(
            r"\b(discount|remise|rabais|rabatt|descuento|sconto|reduction|less\b)\b",
            re.IGNORECASE,
        ),
    ),
    (
        RowType.SHIPPING,
        re.compile(
            r"\b(shipping|freight|delivery|transport|port|envío|livraison|"
            r"frais\s+de\s+port|handling)\b",
            re.IGNORECASE,
        ),
    ),
    (
        RowType.HEADER,
        re.compile(
            r"\b(continued|suite|continued\s+from|page\s+\d+)\b",
            re.IGNORECASE,
        ),
    ),
]


def classify_row_type(description: str | None) -> RowType:
    """Classify a single row based on its description string."""
    if not description:
        return RowType.UNKNOWN
    for row_type, pattern in _PATTERNS:
        if pattern.search(description):
            return row_type
    return RowType.ITEM


def classify_line_items(items: list[RichLineItem]) -> list[RichLineItem]:
    """
    Assign row_type to each item that still has row_type=UNKNOWN or ITEM.

    Items that were already classified by the LLM (not ITEM/UNKNOWN) are left
    as-is to preserve explicit LLM signals.
    """
    classified: list[RichLineItem] = []
    for item in items:
        # Only auto-classify if the LLM left it at ITEM (default) or UNKNOWN
        if item.row_type in (RowType.ITEM, RowType.UNKNOWN):
            inferred = classify_row_type(item.description.value)
            classified.append(item.model_copy(update={"row_type": inferred}))
        else:
            classified.append(item)
    return classified
