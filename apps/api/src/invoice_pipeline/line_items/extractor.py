"""
Phase 4 — Advanced Line Item Extraction: Extractor

Orchestrates rich line item extraction from an Invoice document:
1. Promotes the legacy LineItem list to RichLineItem list (backward compat)
2. Attaches page context from Document.pages where available
3. Runs the row classifier to set row_type
4. Runs the math validator to set math_valid
5. Returns updated list + list of math error strings for review reasons
"""

from __future__ import annotations

import structlog

from invoice_pipeline.line_items.classifier import classify_line_items
from invoice_pipeline.line_items.validator import collect_math_errors, validate_line_item_math
from invoice_pipeline.schemas import (
    CellValue,
    Document,
    FieldValue,
    Invoice,
    RichLineItem,
    RowType,
)

log = structlog.get_logger()


def _field_to_cell(fv: FieldValue, page: int | None = None) -> CellValue:
    """Upcast a FieldValue to a CellValue (Phase 3 → Phase 4 bridge)."""
    return CellValue(
        value=fv.value,
        confidence=fv.confidence,
        evidence=fv.evidence,
        page=page,
        bbox=None,
        source_evidence=None,
    )


def _promote_legacy_items(invoice: Invoice, doc: Document) -> list[RichLineItem]:
    """
    Convert legacy LineItem list to RichLineItem list.

    Uses page=0 for all items when page context is not available from the LLM.
    Preserves all field values and confidences.
    """
    promoted: list[RichLineItem] = []
    default_page: int | None = 0 if doc.pages else None

    for li in invoice.line_items:
        promoted.append(
            RichLineItem(
                description=_field_to_cell(li.description, default_page),
                quantity=_field_to_cell(li.quantity, default_page),
                unit_price=_field_to_cell(li.unit_price, default_page),
                total=_field_to_cell(li.total, default_page),
                row_type=RowType.ITEM,
                math_valid=None,
                page=default_page,
                table_index=0,
            )
        )
    return promoted


def extract_rich_line_items(
    doc: Document,
) -> tuple[list[RichLineItem], list[str]]:
    """
    Main entry point for Phase-4 rich line item extraction.

    Returns:
        (rich_items, math_error_messages)

    The caller should attach rich_items to the invoice and extend
    review_reasons with math_error_messages.
    """
    if doc.extracted is None:
        return [], []

    invoice = doc.extracted

    # Start from any rich items the LLM produced, fall back to legacy items
    if invoice.rich_line_items:
        items = list(invoice.rich_line_items)
        log.info(
            "line_items_source",
            document_id=doc.document_id,
            source="rich_llm",
            count=len(items),
        )
    else:
        items = _promote_legacy_items(invoice, doc)
        log.info(
            "line_items_source",
            document_id=doc.document_id,
            source="legacy_promoted",
            count=len(items),
        )

    if not items:
        return [], []

    # Step 1: Classify row types
    items = classify_line_items(items)

    # Step 2: Validate math consistency
    items = validate_line_item_math(items)

    # Step 3: Collect math errors for review flags
    math_errors = collect_math_errors(items)

    log.info(
        "line_items_extracted",
        document_id=doc.document_id,
        total=len(items),
        math_errors=len(math_errors),
    )

    return items, math_errors
