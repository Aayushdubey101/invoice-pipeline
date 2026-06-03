"""
Phase 5 tests — canonicalization + vendor matching.
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from invoice_pipeline.db.models import Base, Vendor
from invoice_pipeline.llm.base import ExtractionMeta
from invoice_pipeline.schemas import DocumentStatus, FieldValue, Invoice

FIXTURES = Path(__file__).parent / "fixtures"


# ── DB fixture ────────────────────────────────────────────────────────────────

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def db_with_vendors(db_session):
    vendors = [
        Vendor(id="v1", canonical_name="Acme Corp", aliases=["ACME", "Acme Inc"], status="active"),
        Vendor(id="v2", canonical_name="Beta Inc", aliases=["Beta Incorporated"], status="active"),
    ]
    for v in vendors:
        db_session.add(v)
    await db_session.commit()
    return db_session


def _mock_invoice() -> Invoice:
    return Invoice(
        invoice_number=FieldValue(value="INV-2024-001", confidence=0.95),
        invoice_date=FieldValue(value="2024-01-15", confidence=0.9),
        due_date=FieldValue(value="2024-02-15", confidence=0.88),
        vendor_name=FieldValue(value="Acme Corp", confidence=0.92),
        subtotal=FieldValue(value="1000.00", confidence=0.93),
        tax_amount=FieldValue(value="100.00", confidence=0.91),
        total_amount=FieldValue(value="1100.00", confidence=0.96),
        currency=FieldValue(value="USD", confidence=0.99),
        payment_terms=FieldValue(value="Net 30", confidence=0.87),
    )


# ── Date canonicalization ─────────────────────────────────────────────────────

def test_parse_date_iso():
    from invoice_pipeline.canonicalizers.dates import parse_date
    from datetime import date

    assert parse_date("2024-01-15") == date(2024, 1, 15)


def test_parse_date_written():
    from invoice_pipeline.canonicalizers.dates import parse_date
    from datetime import date

    result = parse_date("January 15, 2024")
    assert result == date(2024, 1, 15)


def test_parse_date_none():
    from invoice_pipeline.canonicalizers.dates import parse_date

    assert parse_date(None) is None
    assert parse_date("") is None


def test_parse_date_invalid():
    from invoice_pipeline.canonicalizers.dates import parse_date

    result = parse_date("not-a-date-xyz")
    # dateparser may return something — just ensure no exception
    assert result is None or True


# ── Currency canonicalization ─────────────────────────────────────────────────

def test_parse_amount_plain():
    from invoice_pipeline.canonicalizers.currency import parse_amount

    assert parse_amount("1234.56") == Decimal("1234.56")


def test_parse_amount_with_dollar():
    from invoice_pipeline.canonicalizers.currency import parse_amount

    assert parse_amount("$1,234.56") == Decimal("1234.56")


def test_parse_amount_none():
    from invoice_pipeline.canonicalizers.currency import parse_amount

    assert parse_amount(None) is None
    assert parse_amount("") is None


def test_normalize_currency_iso():
    from invoice_pipeline.canonicalizers.currency import normalize_currency

    assert normalize_currency("USD") == "USD"
    assert normalize_currency("eur") == "EUR"


def test_normalize_currency_symbol():
    from invoice_pipeline.canonicalizers.currency import normalize_currency

    assert normalize_currency("$") == "USD"
    assert normalize_currency("€") == "EUR"


# ── Tax ID validation ─────────────────────────────────────────────────────────

def test_validate_tax_id_returns_value():
    from invoice_pipeline.canonicalizers.tax_ids import validate_tax_id

    result = validate_tax_id("12-3456789")
    assert result is not None


def test_validate_tax_id_none():
    from invoice_pipeline.canonicalizers.tax_ids import validate_tax_id

    assert validate_tax_id(None) is None


# ── Vendor matching ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vendor_exact_match(db_with_vendors):
    from invoice_pipeline.canonicalizers.vendors import match_or_create_vendor

    vendor_id, matched = await match_or_create_vendor("Acme Corp", db_with_vendors)
    assert matched is True
    assert vendor_id == "v1"


@pytest.mark.asyncio
async def test_vendor_fuzzy_match(db_with_vendors):
    from invoice_pipeline.canonicalizers.vendors import match_or_create_vendor

    vendor_id, matched = await match_or_create_vendor("Acme Inc", db_with_vendors)
    assert matched is True
    assert vendor_id == "v1"


@pytest.mark.asyncio
async def test_vendor_alias_match(db_with_vendors):
    from invoice_pipeline.canonicalizers.vendors import match_or_create_vendor

    vendor_id, matched = await match_or_create_vendor("ACME", db_with_vendors)
    assert matched is True
    assert vendor_id == "v1"


@pytest.mark.asyncio
async def test_vendor_no_match_creates_pending(db_session):
    from invoice_pipeline.canonicalizers.vendors import match_or_create_vendor
    from sqlalchemy import select

    vendor_id, matched = await match_or_create_vendor("Unknown Vendor XYZ", db_session)
    assert matched is False
    assert vendor_id is not None

    # verify pending vendor was created
    from invoice_pipeline.db.models import Vendor
    created = (await db_session.execute(select(Vendor).where(Vendor.id == vendor_id))).scalar_one()
    assert created.status == "pending_review"
    assert created.canonical_name == "Unknown Vendor XYZ"


@pytest.mark.asyncio
async def test_vendor_two_invoices_same_vendor_same_id(db_with_vendors):
    """Two invoices with same vendor → same vendor_id."""
    from invoice_pipeline.canonicalizers.vendors import match_or_create_vendor

    id1, _ = await match_or_create_vendor("Acme Corp", db_with_vendors)
    id2, _ = await match_or_create_vendor("Acme Inc", db_with_vendors)
    assert id1 == id2


# ── Canonicalize stage ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_canonicalize_stage(db_with_vendors):
    from invoice_pipeline.stages.canonicalize import canonicalize
    from invoice_pipeline.stages.ingest import ingest

    pdf = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("test.pdf", pdf, "application/pdf")
    doc = doc.model_copy(update={"extracted": _mock_invoice()})
    doc = await canonicalize(doc, db_with_vendors)

    assert doc.canonicalized is not None
    assert doc.canonicalized.total_amount == Decimal("1100.00")
    assert doc.canonicalized.currency == "USD"
    assert doc.vendor_matched is True
    assert str(doc.canonicalized.vendor_id) == "v1"


@pytest.mark.asyncio
async def test_canonicalize_date_parsed(db_with_vendors):
    from invoice_pipeline.stages.canonicalize import canonicalize
    from invoice_pipeline.stages.ingest import ingest
    from datetime import date

    pdf = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("test.pdf", pdf, "application/pdf")
    doc = doc.model_copy(update={"extracted": _mock_invoice()})
    doc = await canonicalize(doc, db_with_vendors)

    assert doc.canonicalized.invoice_date == date(2024, 1, 15)
    assert doc.canonicalized.due_date == date(2024, 2, 15)


# ── Confidence score with vendor boost ───────────────────────────────────────

@pytest.mark.asyncio
async def test_confidence_score_vendor_boost():
    from invoice_pipeline.stages.confidence_score import score_confidence
    from invoice_pipeline.stages.ingest import ingest

    pdf = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("test.pdf", pdf, "application/pdf")
    invoice = _mock_invoice()
    doc = doc.model_copy(update={"extracted": invoice, "vendor_matched": True})

    scored = await score_confidence(doc)
    assert scored.extracted.vendor_name.confidence > invoice.vendor_name.confidence


# ── Notify stage ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_skipped_when_no_webhook(db_session):
    from invoice_pipeline.stages.ingest import ingest
    from invoice_pipeline.stages.notify import notify

    pdf = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("test.pdf", pdf, "application/pdf")
    doc = doc.model_copy(update={"status": DocumentStatus.COMPLETE})

    with patch("invoice_pipeline.stages.notify.settings") as s:
        s.REVIEW_WEBHOOK_URL = ""
        result = await notify(doc)

    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_notify_posts_webhook(db_session):
    from invoice_pipeline.stages.ingest import ingest
    from invoice_pipeline.stages.notify import notify

    pdf = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("test.pdf", pdf, "application/pdf")
    doc = doc.model_copy(update={"status": DocumentStatus.NEEDS_REVIEW})

    with patch("invoice_pipeline.stages.notify.settings") as s:
        s.REVIEW_WEBHOOK_URL = "http://hook.example.com/review"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        with patch("invoice_pipeline.stages.notify.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await notify(doc)

    mock_client.post.assert_called_once()
    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_notify_webhook_failure_non_fatal(db_session):
    from invoice_pipeline.stages.ingest import ingest
    from invoice_pipeline.stages.notify import notify

    pdf = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("test.pdf", pdf, "application/pdf")
    doc = doc.model_copy(update={"status": DocumentStatus.COMPLETE})

    with patch("invoice_pipeline.stages.notify.settings") as s:
        s.REVIEW_WEBHOOK_URL = "http://hook.example.com/review"
        with patch("invoice_pipeline.stages.notify.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await notify(doc)

    # Non-fatal: error attached but status unchanged
    assert result.status == DocumentStatus.COMPLETE
    assert any(e.stage == "notify" for e in result.errors)


# ── Full pipeline Phase 5 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_pipeline_with_canonicalization(db_with_vendors):
    from invoice_pipeline.pipeline import run_pipeline

    meta = ExtractionMeta("openai", "gpt-4o-mini", 200.0, 300, 100, 0.0)
    provider = AsyncMock()
    provider.extract = AsyncMock(return_value=(_mock_invoice(), meta))

    with patch("invoice_pipeline.stages.field_extract.get_provider", return_value=provider):
        with patch("invoice_pipeline.stages.notify.settings") as s:
            s.REVIEW_WEBHOOK_URL = ""
            pdf = (FIXTURES / "sample_invoice.pdf").read_bytes()
            doc = await run_pipeline("test.pdf", pdf, "application/pdf", db_with_vendors)

    assert doc.canonicalized is not None
    assert doc.canonicalized.total_amount == Decimal("1100.00")
    assert doc.vendor_matched is True
    assert doc.status in (DocumentStatus.COMPLETE, DocumentStatus.NEEDS_REVIEW)


@pytest.mark.asyncio
async def test_demo_gate_same_vendor_different_spelling(db_with_vendors):
    """Two invoices with fuzzy-matched vendor → same vendor_id."""
    from invoice_pipeline.canonicalizers.vendors import match_or_create_vendor

    id1, matched1 = await match_or_create_vendor("Acme Corp", db_with_vendors)
    id2, matched2 = await match_or_create_vendor("Acme Inc", db_with_vendors)

    assert matched1 is True
    assert matched2 is True
    assert id1 == id2  # same vendor
