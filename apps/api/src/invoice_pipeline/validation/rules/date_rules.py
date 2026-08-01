"""Date validation rules."""

from invoice_pipeline.canonicalizers.dates import parse_date
from invoice_pipeline.schemas import Invoice
from invoice_pipeline.validation.models import ValidationResult, ValidationStatus
from invoice_pipeline.validation.rules.base import BaseRule, ValidationContext


class InvoiceDateValidRule(BaseRule):
    name = "invoice_date_valid"
    description = "Invoice date must be a parseable, valid date."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        raw = invoice.invoice_date.value
        if not raw or not raw.strip():
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.FAIL,
                message="Invoice date is missing.",
                confidence_impact=-0.1,
                suggested_fix="Enter the invoice date from the document.",
            )

        parsed = parse_date(raw)
        if parsed is None:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.FAIL,
                message=f"Invoice date '{raw}' is not a valid date.",
                confidence_impact=-0.1,
                suggested_fix="Correct the date format (e.g. 2024-01-15).",
            )

        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.PASS,
            message=f"Invoice date '{raw}' is valid (parsed as {parsed.isoformat()}).",
        )


class DueDateAfterInvoiceDateRule(BaseRule):
    name = "due_date_after_invoice_date"
    description = "Due date must be on or after the invoice date."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        inv_raw = invoice.invoice_date.value
        due_raw = invoice.due_date.value

        if not inv_raw or not due_raw:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — invoice date or due date missing.",
            )

        inv_date = parse_date(inv_raw)
        due_date = parse_date(due_raw)

        if inv_date is None or due_date is None:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — could not parse one or both dates.",
            )

        if due_date >= inv_date:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.PASS,
                message=f"Due date ({due_date}) is on or after invoice date ({inv_date}).",
            )

        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.FAIL,
            message=f"Due date ({due_date}) is before invoice date ({inv_date}).",
            confidence_impact=-0.1,
            suggested_fix="Verify the due date — it should not precede the invoice date.",
        )
