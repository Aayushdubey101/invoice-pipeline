"""Currency ISO-4217 validation rule."""

from invoice_pipeline.schemas import Invoice
from invoice_pipeline.validation.models import ValidationResult, ValidationStatus
from invoice_pipeline.validation.rules.base import BaseRule, ValidationContext

# Comprehensive ISO 4217 active currency codes
_ISO_4217_CODES = {
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BRL",
    "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHF", "CLP", "CNY",
    "COP", "CRC", "CUP", "CVE", "CZK", "DJF", "DKK", "DOP", "DZD", "EGP",
    "ERN", "ETB", "EUR", "FJD", "FKP", "GBP", "GEL", "GHS", "GIP", "GMD",
    "GNF", "GTQ", "GYD", "HKD", "HNL", "HRK", "HTG", "HUF", "IDR", "ILS",
    "INR", "IQD", "IRR", "ISK", "JMD", "JOD", "JPY", "KES", "KGS", "KHR",
    "KMF", "KPW", "KRW", "KWD", "KYD", "KZT", "LAK", "LBP", "LKR", "LRD",
    "LSL", "LYD", "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRU",
    "MUR", "MVR", "MWK", "MXN", "MYR", "MZN", "NAD", "NGN", "NIO", "NOK",
    "NPR", "NZD", "OMR", "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG",
    "QAR", "RON", "RSD", "RUB", "RWF", "SAR", "SBD", "SCR", "SDG", "SEK",
    "SGD", "SHP", "SLE", "SLL", "SOS", "SRD", "SSP", "STN", "SVC", "SYP",
    "SZL", "THB", "TJS", "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS",
    "UAH", "UGX", "USD", "UYU", "UZS", "VES", "VND", "VUV", "WST", "XAF",
    "XCD", "XOF", "XPF", "YER", "ZAR", "ZMW", "ZWL",
}


class CurrencyISO4217Rule(BaseRule):
    name = "currency_iso_4217"
    description = "Currency code must be a valid ISO 4217 code."

    async def validate(self, invoice: Invoice, context: ValidationContext) -> ValidationResult:
        raw = invoice.currency.value
        if not raw or not raw.strip():
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.FAIL,
                message="Currency code is missing.",
                confidence_impact=-0.1,
                suggested_fix="Identify the currency from the document.",
            )

        code = raw.strip().upper()
        if code in _ISO_4217_CODES:
            return ValidationResult(
                rule_name=self.name,
                status=ValidationStatus.PASS,
                message=f"Currency '{code}' is a valid ISO 4217 code.",
            )

        return ValidationResult(
            rule_name=self.name,
            status=ValidationStatus.FAIL,
            message=f"Currency '{raw}' is not a recognized ISO 4217 code.",
            confidence_impact=-0.1,
            suggested_fix=f"Replace '{raw}' with a valid 3-letter ISO 4217 code (e.g. USD, EUR, GBP).",
        )
