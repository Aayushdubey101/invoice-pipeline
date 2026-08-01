"""Vendor name validation rule."""

import re

from invoice_pipeline.schemas import Invoice
from invoice_pipeline.validation.models import ValidationResult, ValidationStatus
from invoice_pipeline.validation.rules.base import BaseRule, ValidationContext

# Patterns that suggest garbage extraction
_GARBAGE_RE = re.compile(r"^[\d\W]+$")  # only digits and non-word chars
_MIN_VENDOR_LENGTH = 2


class VendorNameValidRule(BaseRule):
    name = "vendor_name_valid"
    description = "Vendor name must be a plausible business name."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        raw = invoice.vendor_name.value
        if not raw or not raw.strip():
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — vendor name is empty (covered by vendor_exists).",
            )

        name = raw.strip()

        if len(name) < _MIN_VENDOR_LENGTH:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.FAIL,
                message=f"Vendor name '{name}' is too short (min {_MIN_VENDOR_LENGTH} chars).",
                confidence_impact=-0.1,
                suggested_fix="Verify the full vendor name from the document.",
            )

        if _GARBAGE_RE.match(name):
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.FAIL,
                message=f"Vendor name '{name}' appears to be garbage (only digits/symbols).",
                confidence_impact=-0.15,
                suggested_fix="Re-extract the vendor name — current value is not a valid business name.",
            )

        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.PASS,
            message=f"Vendor name '{name}' appears valid.",
        )
