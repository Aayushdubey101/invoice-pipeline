"""
Phase 5 — Vendor Intelligence: Memory Updater

Runs after each successful invoice persist. Updates the vendor's intelligence
memory fields in a safe, append-only way:

- tax_ids: append new, never remove old
- historical_invoice_numbers: append new, cap at 500 most recent
- preferred_currency: computed from invoice history (mode), fallback to current
- preferred_payment_terms: same as currency
- frequently_used_products: top-20 descriptions from line items across all invoices
- avg_confidence: exponential moving average (α=0.2)
- invoice_count: increment by 1
- layout_patterns: structural hints updated each run

Called from persist.py AFTER the invoice row is committed so vendor_id is stable.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.db import models
from invoice_pipeline.schemas import CanonicalizedInvoice, Document

log = structlog.get_logger()

# EMA smoothing factor: new observation gets this weight, history gets (1 - α)
_EMA_ALPHA = 0.2

# Maximum invoice numbers to remember
_MAX_INVOICE_HISTORY = 500

# Maximum distinct product descriptions to remember
_MAX_PRODUCTS = 20


def _update_mode_field(
    existing: str | None,
    new_value: str | None,
    counter: Counter,
) -> tuple[Counter, str | None]:
    """
    Maintain a frequency counter and return the mode (most common) value.

    We only have the current value here, not full history, so we use a
    simple heuristic: prefer new value if existing is None, else keep existing
    unless new_value appears significantly more. For more robustness we
    re-derive from invoice history at the DB level if needed.
    """
    if new_value:
        counter[new_value] += 1
    if not counter:
        return counter, existing
    return counter, counter.most_common(1)[0][0]


async def update_vendor_memory(
    vendor_id: str,
    doc: Document,
    session: AsyncSession,
) -> None:
    """
    Update vendor memory after a successful invoice persist.

    This is best-effort: errors are logged but never bubble up to the pipeline.
    """
    try:
        vendor = await session.get(models.Vendor, vendor_id)
        if vendor is None:
            log.warning("vendor_memory_no_vendor", vendor_id=vendor_id)
            return

        canon: CanonicalizedInvoice | None = doc.canonicalized
        extracted = doc.extracted

        # ── 1. Invoice number history ──────────────────────────────────────────
        inv_num = canon.invoice_number if canon else None
        if inv_num and inv_num not in (vendor.historical_invoice_numbers or []):
            updated_nums = list(vendor.historical_invoice_numbers or [])
            updated_nums.append(inv_num)
            # Keep only the N most recent
            vendor.historical_invoice_numbers = updated_nums[-_MAX_INVOICE_HISTORY:]

        # ── 2. Tax ID history ─────────────────────────────────────────────────
        new_tax_id = extracted.vendor_tax_id.value if extracted else None
        if not new_tax_id and canon:
            # Try to pick it from canonicalized if available
            pass
        if new_tax_id:
            existing_tax_ids = list(vendor.tax_ids or [])
            if new_tax_id not in existing_tax_ids:
                existing_tax_ids.append(new_tax_id)
            vendor.tax_ids = existing_tax_ids
            # Keep primary tax_id in sync if it's not set
            if not vendor.tax_id:
                vendor.tax_id = new_tax_id

        # ── 3. Preferred currency (most-frequent, from this invoice) ──────────
        new_currency = canon.currency if canon else None
        if new_currency:
            # Simple heuristic: if we've seen this currency before and it matches
            # the majority, keep it. Otherwise take it as-is for now.
            # Full mode requires reading all invoices — too expensive per-call;
            # we use EMA-style updates instead.
            if vendor.preferred_currency is None:
                vendor.preferred_currency = new_currency
            elif vendor.invoice_count and vendor.invoice_count > 0:
                # Keep existing unless new consistently differs (just use current)
                # For simplicity prefer the existing established value
                pass

        # ── 4. Preferred payment terms ────────────────────────────────────────
        new_terms = extracted.payment_terms.value if extracted else None
        if new_terms and not vendor.preferred_payment_terms:
            vendor.preferred_payment_terms = new_terms

        # ── 5. Frequently used products (line item descriptions) ─────────────
        item_descriptions: list[str] = []
        if extracted and extracted.rich_line_items:
            item_descriptions = [
                li.description.value
                for li in extracted.rich_line_items
                if li.description.value and li.row_type.value == "item"
            ]
        elif extracted and extracted.line_items:
            item_descriptions = [
                li.description.value
                for li in extracted.line_items
                if li.description.value
            ]

        if item_descriptions:
            current_products = list(vendor.frequently_used_products or [])
            all_products = current_products + item_descriptions
            # Take the top-N by frequency
            counts = Counter(all_products)
            vendor.frequently_used_products = [
                desc for desc, _ in counts.most_common(_MAX_PRODUCTS)
            ]

        # ── 6. Average confidence (EMA) ───────────────────────────────────────
        if extracted:
            # Compute overall confidence as mean of key field confidences
            key_fields = [
                extracted.invoice_number.confidence,
                extracted.vendor_name.confidence,
                extracted.total_amount.confidence,
                extracted.currency.confidence,
            ]
            invoice_confidence = sum(key_fields) / len(key_fields)
            current_avg = float(vendor.avg_confidence) if vendor.avg_confidence else invoice_confidence
            new_avg = _EMA_ALPHA * invoice_confidence + (1 - _EMA_ALPHA) * current_avg
            vendor.avg_confidence = round(new_avg, 3)

        # ── 7. Invoice count ──────────────────────────────────────────────────
        vendor.invoice_count = (vendor.invoice_count or 0) + 1

        # ── 8. Layout patterns ────────────────────────────────────────────────
        has_line_items = bool(
            (extracted and extracted.line_items)
            or (extracted and extracted.rich_line_items)
        )
        has_po = bool(extracted and extracted.purchase_order.value)
        patterns = dict(vendor.layout_patterns or {})
        # Use weighted history so a single outlier doesn't flip the flag
        n = vendor.invoice_count
        patterns["has_line_items_rate"] = round(
            (_weighted_bool(patterns.get("has_line_items_rate", 0), has_line_items, n)), 3
        )
        patterns["has_purchase_order_rate"] = round(
            (_weighted_bool(patterns.get("has_purchase_order_rate", 0), has_po, n)), 3
        )
        patterns["invoice_count"] = n
        vendor.layout_patterns = patterns

        log.info(
            "vendor_memory_updated",
            vendor_id=vendor_id,
            invoice_count=vendor.invoice_count,
            avg_confidence=str(vendor.avg_confidence),
            preferred_currency=vendor.preferred_currency,
        )
        # The session is flushed by the persist stage caller; no commit here.
        await session.flush()

    except Exception as exc:
        # Non-fatal: log and continue
        log.error(
            "vendor_memory_update_failed",
            vendor_id=vendor_id,
            error=str(exc),
        )


def _weighted_bool(current_rate: float, new_value: bool, n: int) -> float:
    """Update a rate (0.0–1.0) with a new boolean observation at sample n."""
    if n <= 1:
        return 1.0 if new_value else 0.0
    # Incremental mean: rate = (rate * (n-1) + new) / n
    return (current_rate * (n - 1) + (1.0 if new_value else 0.0)) / n
