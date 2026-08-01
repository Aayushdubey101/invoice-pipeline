"""Amount and tax validation rules."""

from decimal import Decimal

from invoice_pipeline.canonicalizers.currency import parse_amount
from invoice_pipeline.schemas import Invoice
from invoice_pipeline.validation.models import ValidationResult, ValidationStatus
from invoice_pipeline.validation.rules.base import BaseRule, ValidationContext

# Thresholds
_MAX_REASONABLE_AMOUNT = Decimal("999_999_999_999")  # 1 trillion
_MATH_TOLERANCE_PERCENT = Decimal("0.01")  # 1% tolerance


class DecimalValidationRule(BaseRule):
    name = "decimal_validation"
    description = "Monetary fields must be parseable to Decimal."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        unparseable: list[str] = []
        for field_name in ("subtotal", "tax_amount", "total_amount"):
            fv = getattr(invoice, field_name)
            if fv.value and fv.value.strip():
                result = parse_amount(fv.value)
                if result is None:
                    unparseable.append(field_name)

        if not unparseable:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.PASS,
                message="All monetary fields are valid decimals.",
            )
        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.FAIL,
            message=f"Could not parse as decimal: {', '.join(unparseable)}.",
            confidence_impact=-0.1,
            suggested_fix=f"Correct the numeric format for: {', '.join(unparseable)}.",
        )


class TaxNonNegativeRule(BaseRule):
    name = "tax_non_negative"
    description = "Tax amount must not be negative."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        raw = invoice.tax_amount.value
        if not raw or not raw.strip():
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — tax amount is missing.",
            )

        amount = parse_amount(raw)
        if amount is None:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — tax amount is not parseable.",
            )

        if amount >= 0:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.PASS,
                message=f"Tax amount ({amount}) is non-negative.",
            )

        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.FAIL,
            message=f"Tax amount ({amount}) is negative.",
            confidence_impact=-0.1,
            suggested_fix="Tax amount should be zero or positive. Verify the value.",
        )


class TotalEqualsSubtotalPlusTaxRule(BaseRule):
    name = "total_equals_subtotal_plus_tax"
    description = "Total should equal subtotal + tax (within 1% tolerance)."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        subtotal = parse_amount(invoice.subtotal.value)
        tax = parse_amount(invoice.tax_amount.value)
        total = parse_amount(invoice.total_amount.value)

        if subtotal is None or tax is None or total is None:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — one or more amount fields missing or unparseable.",
            )

        if total == 0:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — total is zero.",
            )

        expected = subtotal + tax
        tolerance = abs(total) * _MATH_TOLERANCE_PERCENT
        diff = abs(expected - total)

        if diff <= tolerance:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.PASS,
                message=f"Math checks out: {subtotal} + {tax} = {expected} ≈ {total}.",
            )

        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.FAIL,
            message=f"Math mismatch: {subtotal} + {tax} = {expected}, but total is {total} (diff: {diff}).",
            confidence_impact=-0.2,
            suggested_fix=f"Expected total: {expected}. Verify subtotal, tax, and total amounts.",
        )


class TaxPercentageValidationRule(BaseRule):
    name = "tax_percentage_validation"
    description = "Tax rate (tax/subtotal) should be between 0% and 100%."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        subtotal = parse_amount(invoice.subtotal.value)
        tax = parse_amount(invoice.tax_amount.value)

        if subtotal is None or tax is None:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — subtotal or tax amount missing.",
            )

        if subtotal == 0:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — subtotal is zero.",
            )

        rate = (tax / subtotal) * 100
        if Decimal("0") <= rate <= Decimal("100"):
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.PASS,
                message=f"Tax rate is {rate:.2f}% — within valid range.",
            )

        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.WARN,
            message=f"Tax rate is {rate:.2f}% — outside 0–100% range.",
            confidence_impact=-0.05,
            suggested_fix="Verify tax and subtotal amounts — the implied tax rate is unusual.",
        )


class InvalidAmountDetectionRule(BaseRule):
    name = "invalid_amount_detection"
    description = "Detect negative totals or absurdly large amounts."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        issues: list[str] = []
        for field_name in ("subtotal", "total_amount"):
            fv = getattr(invoice, field_name)
            if not fv.value or not fv.value.strip():
                continue
            amount = parse_amount(fv.value)
            if amount is None:
                continue
            if amount < 0:
                issues.append(f"{field_name} is negative ({amount})")
            elif amount > _MAX_REASONABLE_AMOUNT:
                issues.append(f"{field_name} exceeds maximum ({amount})")

        if not issues:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.PASS,
                message="All amounts are within valid ranges.",
            )

        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.FAIL,
            message=f"Invalid amounts detected: {'; '.join(issues)}.",
            confidence_impact=-0.15,
            suggested_fix="Review flagged amounts — negative or extremely large values are suspicious.",
        )
