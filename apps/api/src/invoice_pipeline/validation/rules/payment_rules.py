"""Payment terms validation rule."""

import re

from invoice_pipeline.schemas import Invoice
from invoice_pipeline.validation.models import ValidationResult, ValidationStatus
from invoice_pipeline.validation.rules.base import BaseRule, ValidationContext

# Common payment term patterns (case-insensitive)
_PAYMENT_TERM_PATTERNS = [
    re.compile(r"net\s*\d+", re.IGNORECASE),           # Net 30, Net 60
    re.compile(r"due\s+on\s+receipt", re.IGNORECASE),   # Due on receipt
    re.compile(r"cod", re.IGNORECASE),                  # Cash on delivery
    re.compile(r"cia", re.IGNORECASE),                  # Cash in advance
    re.compile(r"prepaid", re.IGNORECASE),
    re.compile(r"\d+\s*days?", re.IGNORECASE),          # 30 days, 60 days
    re.compile(r"\d+/\d+\s*net\s*\d+", re.IGNORECASE),  # 2/10 Net 30
    re.compile(r"eom", re.IGNORECASE),                  # End of month
    re.compile(r"upon\s+completion", re.IGNORECASE),
    re.compile(r"immediate", re.IGNORECASE),
]


class PaymentTermsValidationRule(BaseRule):
    name = "payment_terms_valid"
    description = "Payment terms should match a recognizable format."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        raw = invoice.payment_terms.value
        if not raw or not raw.strip():
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.SKIP,
                message="Skipped — payment terms not provided.",
            )

        terms = raw.strip()
        for pattern in _PAYMENT_TERM_PATTERNS:
            if pattern.search(terms):
                return ValidationResult(
                    rule_name=self.name,
                    status=ValidationStatus.PASS,
                    message=f"Payment terms '{terms}' match a known format.",
                )

        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.WARN,
            message=f"Payment terms '{terms}' do not match common formats.",
            confidence_impact=-0.05,
            suggested_fix="Verify payment terms — expected formats: 'Net 30', 'Due on receipt', etc.",
        )
