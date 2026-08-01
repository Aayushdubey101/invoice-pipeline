"""Tests for Phase 1: Business Rule Validation Engine.

Tests cover:
- Individual validation rules (unit tests)
- Validation engine orchestration
- Pipeline integration
- Edge cases (empty invoices, partial data, Unicode, EU formats)
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from invoice_pipeline.db.models import Base, Invoice as InvoiceModel, Document as DocumentModel, Vendor
from invoice_pipeline.schemas import (
    CanonicalizedInvoice,
    Document,
    DocumentStatus,
    DocumentType,
    FieldValue,
    Invoice,
    LineItem,
)
from invoice_pipeline.validation.engine import ValidationEngine, run_validation
from invoice_pipeline.validation.models import ValidationReport, ValidationResult, ValidationStatus
from invoice_pipeline.validation.rules.amount_rules import (
    DecimalValidationRule,
    InvalidAmountDetectionRule,
    TaxNonNegativeRule,
    TaxPercentageValidationRule,
    TotalEqualsSubtotalPlusTaxRule,
)
from invoice_pipeline.validation.rules.base import BaseRule, ValidationContext
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


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_invoice(**overrides: object) -> Invoice:
    """Create a valid invoice with sensible defaults — override any field."""
    defaults = {
        "invoice_number": FieldValue(value="INV-2024-001", confidence=0.9),
        "invoice_date": FieldValue(value="2024-01-15", confidence=0.9),
        "due_date": FieldValue(value="2024-02-15", confidence=0.9),
        "vendor_name": FieldValue(value="Acme Corporation", confidence=0.9),
        "vendor_address": FieldValue(value="123 Main St, NY", confidence=0.8),
        "vendor_tax_id": FieldValue(value="12-3456789", confidence=0.8),
        "buyer_name": FieldValue(value="Test Buyer Inc", confidence=0.8),
        "buyer_address": FieldValue(value="456 Oak Ave, CA", confidence=0.8),
        "subtotal": FieldValue(value="1000.00", confidence=0.9),
        "tax_amount": FieldValue(value="100.00", confidence=0.9),
        "total_amount": FieldValue(value="1100.00", confidence=0.9),
        "currency": FieldValue(value="USD", confidence=0.9),
        "payment_terms": FieldValue(value="Net 30", confidence=0.8),
        "purchase_order": FieldValue(value="PO-2024-001", confidence=0.8),
    }
    defaults.update(overrides)
    return Invoice(**defaults)


def _make_document(invoice: Invoice | None = None) -> Document:
    return Document(
        document_id="abc123def456",
        filename="test.pdf",
        mime_type="application/pdf",
        raw_text="Invoice INV-2024-001 from Acme Corporation, total $1,100.00",
        extracted=invoice,
        status=DocumentStatus.PROCESSING,
    )


def _make_context(doc: Document | None = None, session: AsyncSession | None = None) -> ValidationContext:
    if doc is None:
        doc = _make_document()
    return ValidationContext(document=doc, raw_text=doc.raw_text, session=session)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


# ═══════════════════════════════════════════════════════════════════════════════
#  UNIT TESTS — Individual Rules
# ═══════════════════════════════════════════════════════════════════════════════


# ── Field Presence Rules ──────────────────────────────────────────────────────


class TestInvoiceNumberExists:
    async def test_pass_when_present(self):
        invoice = _make_invoice()
        ctx = _make_context(_make_document(invoice))
        result = await InvoiceNumberExistsRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_fail_when_missing(self):
        invoice = _make_invoice(invoice_number=FieldValue(value=None))
        ctx = _make_context(_make_document(invoice))
        result = await InvoiceNumberExistsRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL
        assert result.confidence_impact < 0

    async def test_fail_when_empty_string(self):
        invoice = _make_invoice(invoice_number=FieldValue(value=""))
        ctx = _make_context(_make_document(invoice))
        result = await InvoiceNumberExistsRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL

    async def test_fail_when_whitespace_only(self):
        invoice = _make_invoice(invoice_number=FieldValue(value="   "))
        ctx = _make_context(_make_document(invoice))
        result = await InvoiceNumberExistsRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL


class TestVendorExists:
    async def test_pass_when_present(self):
        invoice = _make_invoice()
        ctx = _make_context(_make_document(invoice))
        result = await VendorExistsRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_fail_when_missing(self):
        invoice = _make_invoice(vendor_name=FieldValue(value=None))
        ctx = _make_context(_make_document(invoice))
        result = await VendorExistsRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL


class TestMandatoryFields:
    async def test_pass_all_present(self):
        invoice = _make_invoice()
        ctx = _make_context(_make_document(invoice))
        result = await MandatoryFieldsRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_fail_multiple_missing(self):
        invoice = _make_invoice(
            invoice_number=FieldValue(value=None),
            currency=FieldValue(value=None),
        )
        ctx = _make_context(_make_document(invoice))
        result = await MandatoryFieldsRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL
        assert "invoice_number" in result.message
        assert "currency" in result.message

    async def test_impact_proportional_to_missing_count(self):
        invoice = _make_invoice(
            invoice_number=FieldValue(value=None),
            vendor_name=FieldValue(value=None),
            total_amount=FieldValue(value=None),
        )
        ctx = _make_context(_make_document(invoice))
        result = await MandatoryFieldsRule().validate(invoice, ctx)
        assert result.confidence_impact == pytest.approx(-0.15)


# ── Date Rules ────────────────────────────────────────────────────────────────


class TestInvoiceDateValid:
    async def test_pass_iso_date(self):
        invoice = _make_invoice(invoice_date=FieldValue(value="2024-01-15"))
        ctx = _make_context(_make_document(invoice))
        result = await InvoiceDateValidRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_pass_written_date(self):
        invoice = _make_invoice(invoice_date=FieldValue(value="January 15, 2024"))
        ctx = _make_context(_make_document(invoice))
        result = await InvoiceDateValidRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_fail_invalid_date(self):
        invoice = _make_invoice(invoice_date=FieldValue(value="not-a-date-xyz"))
        ctx = _make_context(_make_document(invoice))
        result = await InvoiceDateValidRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL

    async def test_fail_missing_date(self):
        invoice = _make_invoice(invoice_date=FieldValue(value=None))
        ctx = _make_context(_make_document(invoice))
        result = await InvoiceDateValidRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL


class TestDueDateAfterInvoiceDate:
    async def test_pass_due_after_invoice(self):
        invoice = _make_invoice(
            invoice_date=FieldValue(value="2024-01-01"),
            due_date=FieldValue(value="2024-02-01"),
        )
        ctx = _make_context(_make_document(invoice))
        result = await DueDateAfterInvoiceDateRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_pass_same_day(self):
        invoice = _make_invoice(
            invoice_date=FieldValue(value="2024-01-01"),
            due_date=FieldValue(value="2024-01-01"),
        )
        ctx = _make_context(_make_document(invoice))
        result = await DueDateAfterInvoiceDateRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_fail_due_before_invoice(self):
        invoice = _make_invoice(
            invoice_date=FieldValue(value="2024-06-15"),
            due_date=FieldValue(value="2024-05-01"),
        )
        ctx = _make_context(_make_document(invoice))
        result = await DueDateAfterInvoiceDateRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL

    async def test_skip_when_missing_dates(self):
        invoice = _make_invoice(due_date=FieldValue(value=None))
        ctx = _make_context(_make_document(invoice))
        result = await DueDateAfterInvoiceDateRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.SKIP


# ── Currency Rules ────────────────────────────────────────────────────────────


class TestCurrencyISO4217:
    async def test_pass_usd(self):
        invoice = _make_invoice(currency=FieldValue(value="USD"))
        ctx = _make_context(_make_document(invoice))
        result = await CurrencyISO4217Rule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_pass_eur(self):
        invoice = _make_invoice(currency=FieldValue(value="EUR"))
        ctx = _make_context(_make_document(invoice))
        result = await CurrencyISO4217Rule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_pass_lowercase(self):
        """Currency codes are case-insensitive."""
        invoice = _make_invoice(currency=FieldValue(value="gbp"))
        ctx = _make_context(_make_document(invoice))
        result = await CurrencyISO4217Rule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_fail_invalid_code(self):
        invoice = _make_invoice(currency=FieldValue(value="XYZ"))
        ctx = _make_context(_make_document(invoice))
        result = await CurrencyISO4217Rule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL

    async def test_fail_missing(self):
        invoice = _make_invoice(currency=FieldValue(value=None))
        ctx = _make_context(_make_document(invoice))
        result = await CurrencyISO4217Rule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL


# ── Amount Rules ──────────────────────────────────────────────────────────────


class TestDecimalValidation:
    async def test_pass_valid_amounts(self):
        invoice = _make_invoice()
        ctx = _make_context(_make_document(invoice))
        result = await DecimalValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_pass_eu_format(self):
        invoice = _make_invoice(
            subtotal=FieldValue(value="1.000,00"),
            tax_amount=FieldValue(value="100,00"),
            total_amount=FieldValue(value="1.100,00"),
        )
        ctx = _make_context(_make_document(invoice))
        result = await DecimalValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_fail_unparseable(self):
        invoice = _make_invoice(total_amount=FieldValue(value="abc-not-number"))
        ctx = _make_context(_make_document(invoice))
        result = await DecimalValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL
        assert "total_amount" in result.message


class TestTaxNonNegative:
    async def test_pass_positive(self):
        invoice = _make_invoice(tax_amount=FieldValue(value="100.00"))
        ctx = _make_context(_make_document(invoice))
        result = await TaxNonNegativeRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_pass_zero(self):
        invoice = _make_invoice(tax_amount=FieldValue(value="0.00"))
        ctx = _make_context(_make_document(invoice))
        result = await TaxNonNegativeRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_fail_negative(self):
        invoice = _make_invoice(tax_amount=FieldValue(value="-50.00"))
        ctx = _make_context(_make_document(invoice))
        result = await TaxNonNegativeRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL

    async def test_skip_missing(self):
        invoice = _make_invoice(tax_amount=FieldValue(value=None))
        ctx = _make_context(_make_document(invoice))
        result = await TaxNonNegativeRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.SKIP


class TestTotalEqualsSubtotalPlusTax:
    async def test_pass_exact_match(self):
        invoice = _make_invoice(
            subtotal=FieldValue(value="1000.00"),
            tax_amount=FieldValue(value="100.00"),
            total_amount=FieldValue(value="1100.00"),
        )
        ctx = _make_context(_make_document(invoice))
        result = await TotalEqualsSubtotalPlusTaxRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_pass_within_tolerance(self):
        # 1% tolerance: total=1100, expected=1100, diff must be <= 11
        invoice = _make_invoice(
            subtotal=FieldValue(value="1000.00"),
            tax_amount=FieldValue(value="100.00"),
            total_amount=FieldValue(value="1105.00"),
        )
        ctx = _make_context(_make_document(invoice))
        result = await TotalEqualsSubtotalPlusTaxRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_fail_large_mismatch(self):
        invoice = _make_invoice(
            subtotal=FieldValue(value="1000.00"),
            tax_amount=FieldValue(value="100.00"),
            total_amount=FieldValue(value="2000.00"),
        )
        ctx = _make_context(_make_document(invoice))
        result = await TotalEqualsSubtotalPlusTaxRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL

    async def test_skip_when_field_missing(self):
        invoice = _make_invoice(subtotal=FieldValue(value=None))
        ctx = _make_context(_make_document(invoice))
        result = await TotalEqualsSubtotalPlusTaxRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.SKIP


class TestTaxPercentage:
    async def test_pass_reasonable_rate(self):
        invoice = _make_invoice(
            subtotal=FieldValue(value="1000.00"),
            tax_amount=FieldValue(value="100.00"),
        )
        ctx = _make_context(_make_document(invoice))
        result = await TaxPercentageValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_warn_over_100_percent(self):
        invoice = _make_invoice(
            subtotal=FieldValue(value="100.00"),
            tax_amount=FieldValue(value="200.00"),
        )
        ctx = _make_context(_make_document(invoice))
        result = await TaxPercentageValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.WARN

    async def test_skip_zero_subtotal(self):
        invoice = _make_invoice(subtotal=FieldValue(value="0.00"))
        ctx = _make_context(_make_document(invoice))
        result = await TaxPercentageValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.SKIP


class TestInvalidAmountDetection:
    async def test_pass_valid_amounts(self):
        invoice = _make_invoice()
        ctx = _make_context(_make_document(invoice))
        result = await InvalidAmountDetectionRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_fail_negative_total(self):
        invoice = _make_invoice(total_amount=FieldValue(value="-500.00"))
        ctx = _make_context(_make_document(invoice))
        result = await InvalidAmountDetectionRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL

    async def test_fail_absurdly_large(self):
        invoice = _make_invoice(total_amount=FieldValue(value="99999999999999.00"))
        ctx = _make_context(_make_document(invoice))
        result = await InvalidAmountDetectionRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL


# ── Vendor Rules ──────────────────────────────────────────────────────────────


class TestVendorNameValid:
    async def test_pass_valid_name(self):
        invoice = _make_invoice(vendor_name=FieldValue(value="Acme Corporation"))
        ctx = _make_context(_make_document(invoice))
        result = await VendorNameValidRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_fail_too_short(self):
        invoice = _make_invoice(vendor_name=FieldValue(value="A"))
        ctx = _make_context(_make_document(invoice))
        result = await VendorNameValidRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL

    async def test_fail_garbage_chars(self):
        invoice = _make_invoice(vendor_name=FieldValue(value="12345"))
        ctx = _make_context(_make_document(invoice))
        result = await VendorNameValidRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.FAIL

    async def test_skip_empty(self):
        invoice = _make_invoice(vendor_name=FieldValue(value=""))
        ctx = _make_context(_make_document(invoice))
        result = await VendorNameValidRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.SKIP

    async def test_pass_unicode_name(self):
        invoice = _make_invoice(vendor_name=FieldValue(value="Société Générale"))
        ctx = _make_context(_make_document(invoice))
        result = await VendorNameValidRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS


# ── Payment Rules ─────────────────────────────────────────────────────────────


class TestPaymentTermsValidation:
    async def test_pass_net_30(self):
        invoice = _make_invoice(payment_terms=FieldValue(value="Net 30"))
        ctx = _make_context(_make_document(invoice))
        result = await PaymentTermsValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_pass_due_on_receipt(self):
        invoice = _make_invoice(payment_terms=FieldValue(value="Due on receipt"))
        ctx = _make_context(_make_document(invoice))
        result = await PaymentTermsValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_pass_discount_terms(self):
        invoice = _make_invoice(payment_terms=FieldValue(value="2/10 Net 30"))
        ctx = _make_context(_make_document(invoice))
        result = await PaymentTermsValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_warn_unrecognized(self):
        invoice = _make_invoice(payment_terms=FieldValue(value="xyzzy123"))
        ctx = _make_context(_make_document(invoice))
        result = await PaymentTermsValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.WARN

    async def test_skip_empty(self):
        invoice = _make_invoice(payment_terms=FieldValue(value=None))
        ctx = _make_context(_make_document(invoice))
        result = await PaymentTermsValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.SKIP


# ── Duplicate Rules ───────────────────────────────────────────────────────────


class TestDuplicateInvoiceDetection:
    async def test_pass_no_duplicate(self, db_session: AsyncSession):
        invoice = _make_invoice()
        doc = _make_document(invoice)
        ctx = _make_context(doc, session=db_session)
        result = await DuplicateInvoiceDetectionRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_warn_duplicate_found(self, db_session: AsyncSession):
        # Seed existing invoice in DB
        db_doc = DocumentModel(
            id="existing_doc_hash",
            filename="old.pdf",
            mime_type="application/pdf",
            file_size_bytes=100,
            status="complete",
        )
        db_session.add(db_doc)
        db_inv = InvoiceModel(
            document_id="existing_doc_hash",
            invoice_number="INV-2024-001",
        )
        db_session.add(db_inv)
        await db_session.flush()

        invoice = _make_invoice()
        doc = _make_document(invoice)
        ctx = _make_context(doc, session=db_session)
        result = await DuplicateInvoiceDetectionRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.WARN
        assert "duplicate" in result.message.lower()

    async def test_skip_no_invoice_number(self):
        invoice = _make_invoice(invoice_number=FieldValue(value=None))
        doc = _make_document(invoice)
        ctx = _make_context(doc, session=None)
        result = await DuplicateInvoiceDetectionRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.SKIP

    async def test_skip_no_session(self):
        invoice = _make_invoice()
        doc = _make_document(invoice)
        ctx = _make_context(doc, session=None)
        result = await DuplicateInvoiceDetectionRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.SKIP


# ═══════════════════════════════════════════════════════════════════════════════
#  INTEGRATION TESTS — Engine
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidationEngine:
    async def test_all_pass_valid_invoice(self):
        """A well-formed invoice should pass most rules."""
        invoice = _make_invoice()
        doc = _make_document(invoice)
        ctx = _make_context(doc)
        engine = ValidationEngine()
        report = await engine.validate(invoice, ctx)

        assert report.passed > 0
        assert report.failed == 0  # no DB session → duplicate is SKIP

    async def test_never_terminates_on_failure(self):
        """All rules must execute even when some fail."""
        # Create an invoice with multiple problems
        invoice = _make_invoice(
            invoice_number=FieldValue(value=None),
            vendor_name=FieldValue(value=None),
            currency=FieldValue(value="INVALID"),
            total_amount=FieldValue(value="-999.99"),
        )
        doc = _make_document(invoice)
        ctx = _make_context(doc)
        engine = ValidationEngine()
        report = await engine.validate(invoice, ctx)

        # Should have run ALL rules regardless of failures
        total = report.passed + report.failed + report.warnings + report.skipped
        assert total == len(engine.rules)
        assert report.failed > 0

    async def test_report_counts_accurate(self):
        invoice = _make_invoice()
        doc = _make_document(invoice)
        ctx = _make_context(doc)
        engine = ValidationEngine()
        report = await engine.validate(invoice, ctx)

        counted_pass = sum(1 for r in report.results if r.status == ValidationStatus.PASS)
        counted_fail = sum(1 for r in report.results if r.status == ValidationStatus.FAIL)
        assert report.passed == counted_pass
        assert report.failed == counted_fail

    async def test_engine_with_custom_rules(self):
        """Engine accepts a custom rule list."""
        invoice = _make_invoice()
        doc = _make_document(invoice)
        ctx = _make_context(doc)
        engine = ValidationEngine(rules=[InvoiceNumberExistsRule()])
        report = await engine.validate(invoice, ctx)

        assert len(report.results) == 1
        assert report.results[0].rule_name == "invoice_number_exists"

    async def test_engine_handles_rule_exception(self):
        """If a rule raises unexpectedly, engine catches and SKIPs it."""

        class BrokenRule(BaseRule):
            name = "broken_rule"
            description = "Always explodes"

            async def validate(self, invoice, context):
                raise RuntimeError("boom")

        invoice = _make_invoice()
        doc = _make_document(invoice)
        ctx = _make_context(doc)
        engine = ValidationEngine(rules=[BrokenRule(), InvoiceNumberExistsRule()])
        report = await engine.validate(invoice, ctx)

        assert len(report.results) == 2
        assert report.results[0].status == ValidationStatus.SKIP
        assert "boom" in report.results[0].message
        assert report.results[1].status == ValidationStatus.PASS


class TestValidationReport:
    def test_is_valid_when_no_failures(self):
        report = ValidationReport(
            results=[
                ValidationResult(rule_name="r1", status=ValidationStatus.PASS, message="ok"),
                ValidationResult(rule_name="r2", status=ValidationStatus.WARN, message="warn"),
            ],
            passed=1,
            failed=0,
            warnings=1,
            skipped=0,
        )
        assert report.is_valid is True

    def test_is_not_valid_when_failures(self):
        report = ValidationReport(
            results=[
                ValidationResult(rule_name="r1", status=ValidationStatus.FAIL, message="bad"),
            ],
            passed=0,
            failed=1,
            warnings=0,
            skipped=0,
        )
        assert report.is_valid is False

    def test_total_confidence_impact(self):
        report = ValidationReport(
            results=[
                ValidationResult(rule_name="r1", status=ValidationStatus.FAIL, message="a", confidence_impact=-0.1),
                ValidationResult(rule_name="r2", status=ValidationStatus.FAIL, message="b", confidence_impact=-0.2),
                ValidationResult(rule_name="r3", status=ValidationStatus.PASS, message="c", confidence_impact=0.0),
            ],
            passed=1,
            failed=2,
            warnings=0,
            skipped=0,
        )
        assert report.total_confidence_impact == pytest.approx(-0.3)


# ═══════════════════════════════════════════════════════════════════════════════
#  CONVENIENCE FUNCTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunValidation:
    async def test_returns_empty_report_for_no_extraction(self):
        doc = _make_document(invoice=None)
        report = await run_validation(doc)
        assert len(report.results) == 0

    async def test_returns_full_report_for_valid_invoice(self):
        invoice = _make_invoice()
        doc = _make_document(invoice)
        report = await run_validation(doc)
        assert len(report.results) > 0
        assert report.passed > 0


# ═══════════════════════════════════════════════════════════════════════════════
#  EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    async def test_empty_invoice_all_defaults(self):
        """An Invoice with all defaults should not crash any rule."""
        invoice = Invoice()
        doc = _make_document(invoice)
        ctx = _make_context(doc)
        engine = ValidationEngine()
        report = await engine.validate(invoice, ctx)
        total = report.passed + report.failed + report.warnings + report.skipped
        assert total == len(engine.rules)

    async def test_unicode_vendor_name(self):
        invoice = _make_invoice(vendor_name=FieldValue(value="日本電気株式会社"))
        doc = _make_document(invoice)
        ctx = _make_context(doc)
        result = await VendorNameValidRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_eu_amounts_with_spaces(self):
        """European amounts with space thousands separators."""
        invoice = _make_invoice(
            subtotal=FieldValue(value="75 974,00"),
            tax_amount=FieldValue(value="6 029,30"),
            total_amount=FieldValue(value="82 003,30"),
        )
        doc = _make_document(invoice)
        ctx = _make_context(doc)
        result = await DecimalValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_payment_terms_60_days(self):
        invoice = _make_invoice(payment_terms=FieldValue(value="60 days"))
        ctx = _make_context(_make_document(invoice))
        result = await PaymentTermsValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS

    async def test_payment_terms_eom(self):
        invoice = _make_invoice(payment_terms=FieldValue(value="EOM"))
        ctx = _make_context(_make_document(invoice))
        result = await PaymentTermsValidationRule().validate(invoice, ctx)
        assert result.status == ValidationStatus.PASS
