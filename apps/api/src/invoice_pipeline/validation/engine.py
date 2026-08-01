"""Validation engine — orchestrates all rules against an extracted invoice."""

import structlog

from invoice_pipeline.schemas import Document, Invoice
from invoice_pipeline.validation.models import ValidationReport, ValidationResult, ValidationStatus
from invoice_pipeline.validation.rules import ALL_RULES
from invoice_pipeline.validation.rules.base import BaseRule, ValidationContext

log = structlog.get_logger()


class ValidationEngine:
    """Runs all registered validation rules and produces a ValidationReport.

    Never terminates processing after one failure — always runs all rules
    and generates a complete report.
    """

    def __init__(self, rules: list[BaseRule] | None = None) -> None:
        self.rules = rules if rules is not None else list(ALL_RULES)

    async def validate(
        self,
        invoice: Invoice,
        context: ValidationContext,
    ) -> ValidationReport:
        """Execute all rules and return an aggregated report."""
        results: list[ValidationResult] = []

        for rule in self.rules:
            try:
                result = await rule.validate(invoice, context)
                results.append(result)
            except Exception as exc:
                log.error(
                    "validation_rule_error",
                    rule=rule.name,
                    error=str(exc),
                )
                results.append(
                    ValidationResult(
                        rule_name=rule.name,
                        status=ValidationStatus.SKIP,
                        message=f"Rule error: {exc}",
                    )
                )

        passed = sum(1 for r in results if r.status == ValidationStatus.PASS)
        failed = sum(1 for r in results if r.status == ValidationStatus.FAIL)
        warnings = sum(1 for r in results if r.status == ValidationStatus.WARN)
        skipped = sum(1 for r in results if r.status == ValidationStatus.SKIP)

        report = ValidationReport(
            results=results,
            passed=passed,
            failed=failed,
            warnings=warnings,
            skipped=skipped,
        )

        log.info(
            "validation_complete",
            passed=passed,
            failed=failed,
            warnings=warnings,
            skipped=skipped,
            is_valid=report.is_valid,
        )

        return report


async def run_validation(doc: Document) -> ValidationReport:
    """Convenience function to validate a Document's extracted invoice.

    Returns an empty report if no extraction is available.
    """
    if doc.extracted is None:
        return ValidationReport()

    context = ValidationContext(
        document=doc,
        raw_text=doc.raw_text,
    )
    engine = ValidationEngine()
    return await engine.validate(doc.extracted, context)
