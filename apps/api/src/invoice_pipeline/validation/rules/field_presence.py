"""Field presence validation rules."""

from invoice_pipeline.schemas import Invoice
from invoice_pipeline.validation.models import ValidationResult, ValidationStatus
from invoice_pipeline.validation.rules.base import BaseRule, ValidationContext

_MANDATORY_FIELDS = (
    "invoice_number",
    "vendor_name",
    "invoice_date",
    "total_amount",
    "currency",
)


class InvoiceNumberExistsRule(BaseRule):
    name = "invoice_number_exists"
    description = "Invoice number must be present."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        fv = invoice.invoice_number
        if fv.value and fv.value.strip():
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.PASS,
                message="Invoice number is present.",
            )
        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.FAIL,
            message="Invoice number is missing.",
            confidence_impact=-0.15,
            suggested_fix="Manually enter the invoice number from the document.",
        )


class VendorExistsRule(BaseRule):
    name = "vendor_exists"
    description = "Vendor name must be present."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        fv = invoice.vendor_name
        if fv.value and fv.value.strip():
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.PASS,
                message="Vendor name is present.",
            )
        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.FAIL,
            message="Vendor name is missing.",
            confidence_impact=-0.15,
            suggested_fix="Identify the vendor from the document header or logo.",
        )


class MandatoryFieldsRule(BaseRule):
    name = "mandatory_fields"
    description = "All critical fields must have values."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        missing: list[str] = []
        for field_name in _MANDATORY_FIELDS:
            fv = getattr(invoice, field_name, None)
            if fv is None or not fv.value or not fv.value.strip():
                missing.append(field_name)

        if not missing:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.PASS,
                message="All mandatory fields are present.",
            )
        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.FAIL,
            message=f"Missing mandatory fields: {', '.join(missing)}.",
            confidence_impact=-0.05 * len(missing),
            suggested_fix=f"Review the document and fill in: {', '.join(missing)}.",
        )
