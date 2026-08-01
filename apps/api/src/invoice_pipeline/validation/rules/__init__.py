"""Validation rule registry — collects all available rules."""

from invoice_pipeline.validation.rules.amount_rules import (
    DecimalValidationRule,
    InvalidAmountDetectionRule,
    TaxPercentageValidationRule,
    TotalEqualsSubtotalPlusTaxRule,
    TaxNonNegativeRule,
)
from invoice_pipeline.validation.rules.currency_rules import CurrencyISO4217Rule
from invoice_pipeline.validation.rules.date_rules import DueDateAfterInvoiceDateRule, InvoiceDateValidRule
from invoice_pipeline.validation.rules.duplicate_rules import DuplicateInvoiceDetectionRule
from invoice_pipeline.validation.rules.field_presence import (
    InvoiceNumberExistsRule,
    MandatoryFieldsRule,
    VendorExistsRule,
)
from invoice_pipeline.validation.rules.payment_rules import PaymentTermsValidationRule
from invoice_pipeline.validation.rules.vendor_rules import VendorNameValidRule

ALL_RULES = [
    InvoiceNumberExistsRule(),
    VendorExistsRule(),
    VendorNameValidRule(),
    InvoiceDateValidRule(),
    DueDateAfterInvoiceDateRule(),
    CurrencyISO4217Rule(),
    DecimalValidationRule(),
    TaxNonNegativeRule(),
    TotalEqualsSubtotalPlusTaxRule(),
    DuplicateInvoiceDetectionRule(),
    MandatoryFieldsRule(),
    PaymentTermsValidationRule(),
    TaxPercentageValidationRule(),
    InvalidAmountDetectionRule(),
]

__all__ = ["ALL_RULES"]
