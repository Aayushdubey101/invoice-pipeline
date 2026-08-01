"""Duplicate invoice detection rule (requires DB session)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.db import models
from invoice_pipeline.schemas import Invoice
from invoice_pipeline.validation.models import ValidationResult, ValidationStatus
from invoice_pipeline.validation.rules.base import BaseRule, ValidationContext


class DuplicateInvoiceDetectionRule(BaseRule):
    name = "duplicate_invoice_detection"
    description = "Detect if the same invoice number + vendor already exists."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        inv_num = invoice.invoice_number.value
        vendor_name = invoice.vendor_name.value

        if not inv_num or not inv_num.strip():
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — no invoice number to check.",
            )

        if context.session is None:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — no database session available.",
            )

        try:
            existing = await _find_duplicate(
                context.session,
                inv_num.strip(),
                vendor_name.strip() if vendor_name else None,
                exclude_document_id=context.document.document_id,
            )

            if existing is None:
                return ValidationResult(
                    rule_name=self.name,
                    status=ValidationStatus.PASS,
                    message=f"No duplicate found for invoice '{inv_num}'.",
                )

            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.WARN,
                message=(
                    f"Potential duplicate: invoice '{inv_num}' already exists "
                    f"(document_id={existing.document_id})."
                ),
                confidence_impact=-0.1,
                suggested_fix="Review whether this is a genuine duplicate or a different invoice.",
            )
        except Exception as exc:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message=f"Skipped — database error: {exc}",
            )


async def _find_duplicate(
    session: AsyncSession,
    invoice_number: str,
    vendor_name: str | None,
    exclude_document_id: str,
) -> models.Invoice | None:
    """Check if an invoice with the same number (and optionally vendor) exists."""
    stmt = (
        select(models.Invoice)
        .where(models.Invoice.invoice_number == invoice_number)
        .where(models.Invoice.document_id != exclude_document_id)
    )

    result = await session.execute(stmt)
    candidates = result.scalars().all()

    if not candidates:
        return None

    # If vendor name available, narrow to same vendor
    if vendor_name:
        for candidate in candidates:
            # Load vendor to check name match
            if candidate.vendor_id:
                vendor = await session.get(models.Vendor, candidate.vendor_id)
                if vendor and vendor.canonical_name and _names_similar(vendor.canonical_name, vendor_name):
                    return candidate
        # No vendor match but same invoice number is still suspicious
        return candidates[0] if candidates else None

    return candidates[0]


def _names_similar(a: str, b: str) -> bool:
    """Simple case-insensitive comparison for vendor name similarity."""
    return a.strip().lower() == b.strip().lower()
