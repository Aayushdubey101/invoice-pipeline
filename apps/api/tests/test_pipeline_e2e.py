"""
Phase 3 E2E pipeline tests.
Uses SQLite in-memory DB + mocked LLM provider.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_pipeline.db.models import Base
from invoice_pipeline.llm.base import ExtractionMeta
from invoice_pipeline.schemas import DocumentStatus, DocumentType, FieldValue, Invoice

FIXTURES = Path(__file__).parent / "fixtures"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _mock_invoice_response() -> Invoice:
    return Invoice(
        invoice_number=FieldValue(value="INV-2024-001", confidence=0.95, evidence="INV-2024-001"),
        invoice_date=FieldValue(value="2024-01-15", confidence=0.9, evidence="2024-01-15"),
        due_date=FieldValue(value="2024-02-15", confidence=0.88, evidence="2024-02-15"),
        vendor_name=FieldValue(value="Acme Corp", confidence=0.92, evidence="Acme Corp"),
        buyer_name=FieldValue(value="Beta Inc", confidence=0.85, evidence="Beta Inc"),
        subtotal=FieldValue(value="1000.00", confidence=0.93, evidence="$1000.00"),
        tax_amount=FieldValue(value="100.00", confidence=0.91, evidence="$100.00"),
        total_amount=FieldValue(value="1100.00", confidence=0.96, evidence="$1100.00"),
        currency=FieldValue(value="USD", confidence=0.99, evidence="USD"),
        payment_terms=FieldValue(value="Net 30", confidence=0.87, evidence="Net 30"),
    )


def _mock_meta() -> ExtractionMeta:
    return ExtractionMeta(
        provider_name="openai",
        model_name="gpt-4o-mini",
        latency_ms=250.0,
        tokens_in=400,
        tokens_out=150,
        cost_estimate=0.0005,
    )


@pytest.fixture
def mock_llm():
    invoice = _mock_invoice_response()
    meta = _mock_meta()
    mock_provider = AsyncMock()
    mock_provider.extract = AsyncMock(return_value=(invoice, meta))
    with patch("invoice_pipeline.llm.factory._provider_instance", mock_provider):
        with patch(
            "invoice_pipeline.stages.field_extract.get_provider", return_value=mock_provider
        ):
            yield mock_provider


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_stage():
    from invoice_pipeline.stages.ingest import ingest

    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("sample_invoice.pdf", pdf_bytes, "application/pdf")

    assert len(doc.document_id) == 64  # SHA256 hex
    assert doc.filename == "sample_invoice.pdf"
    assert doc.status == DocumentStatus.PROCESSING
    assert doc.file_bytes == pdf_bytes


@pytest.mark.asyncio
async def test_ingest_rejects_unsupported_mime():
    from invoice_pipeline.stages.ingest import ingest

    with pytest.raises(ValueError, match="Unsupported MIME type"):
        await ingest("file.exe", b"MZ\x90\x00", "application/x-msdownload")


@pytest.mark.asyncio
async def test_ingest_idempotency():
    from invoice_pipeline.stages.ingest import ingest

    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc1 = await ingest("inv1.pdf", pdf_bytes, "application/pdf")
    doc2 = await ingest("inv2.pdf", pdf_bytes, "application/pdf")
    assert doc1.document_id == doc2.document_id  # same bytes → same SHA256


@pytest.mark.asyncio
async def test_classify_pdf():
    from invoice_pipeline.stages.classify import classify
    from invoice_pipeline.stages.ingest import ingest

    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("sample_invoice.pdf", pdf_bytes, "application/pdf")
    classified = await classify(doc)

    assert classified.doc_type in (DocumentType.TEXT_PDF, DocumentType.SCANNED_PDF)


@pytest.mark.asyncio
async def test_classify_image():
    from invoice_pipeline.stages.classify import classify
    from invoice_pipeline.stages.ingest import ingest

    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    doc = await ingest("scan.png", fake_png, "image/png")
    classified = await classify(doc)

    assert classified.doc_type == DocumentType.IMAGE


@pytest.mark.asyncio
async def test_text_extract_pdf():
    from invoice_pipeline.stages.classify import classify
    from invoice_pipeline.stages.ingest import ingest
    from invoice_pipeline.stages.text_extract import text_extract

    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("sample_invoice.pdf", pdf_bytes, "application/pdf")
    doc = await classify(doc)
    doc = await text_extract(doc)

    assert len(doc.pages) > 0
    assert "INV" in doc.raw_text or "Invoice" in doc.raw_text


@pytest.mark.asyncio
async def test_field_extract_calls_llm(mock_llm, db_session: AsyncSession):
    from invoice_pipeline.stages.field_extract import field_extract
    from invoice_pipeline.stages.ingest import ingest

    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("sample_invoice.pdf", pdf_bytes, "application/pdf")
    doc = doc.model_copy(update={"raw_text": "Invoice Number: INV-2024-001\nTotal: $1100.00 USD"})
    doc = await field_extract(doc)

    assert doc.extracted is not None
    assert doc.extracted.invoice_number.value == "INV-2024-001"
    assert mock_llm.extract.called


@pytest.mark.asyncio
async def test_confidence_score_boosts_known_currency():
    from invoice_pipeline.stages.confidence_score import score_confidence
    from invoice_pipeline.stages.ingest import ingest

    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("test.pdf", pdf_bytes, "application/pdf")
    invoice = _mock_invoice_response()
    doc = doc.model_copy(update={"extracted": invoice})

    scored = await score_confidence(doc)
    assert scored.extracted is not None
    assert scored.extracted.currency.confidence >= invoice.currency.confidence


@pytest.mark.asyncio
async def test_confidence_score_flags_low_confidence():
    from invoice_pipeline.stages.confidence_score import score_confidence
    from invoice_pipeline.stages.ingest import ingest

    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("test.pdf", pdf_bytes, "application/pdf")
    low_confidence_invoice = Invoice(
        invoice_number=FieldValue(value="INV-001", confidence=0.4),
        total_amount=FieldValue(value="100.00", confidence=0.3),
    )
    doc = doc.model_copy(update={"extracted": low_confidence_invoice})

    scored = await score_confidence(doc)
    assert scored.canonicalized is not None
    assert scored.canonicalized.needs_review is True
    assert len(scored.canonicalized.review_reasons) > 0


@pytest.mark.asyncio
async def test_full_pipeline_text_pdf(mock_llm, db_session: AsyncSession):
    from invoice_pipeline.pipeline import run_pipeline

    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await run_pipeline(
        filename="sample_invoice.pdf",
        file_bytes=pdf_bytes,
        mime_type="application/pdf",
        session=db_session,
    )

    assert doc.document_id is not None
    assert doc.status in (DocumentStatus.COMPLETE, DocumentStatus.NEEDS_REVIEW)
    assert doc.extracted is not None
    # If tesseract isn't in PATH on Windows, OCR might generate a non-fatal error. Allow up to 1.
    assert len(doc.errors) <= 1


@pytest.mark.asyncio
async def test_pipeline_idempotent_same_file(mock_llm, db_session: AsyncSession):
    """Same file bytes → same document_id → second run is an upsert, not a duplicate."""
    from invoice_pipeline.pipeline import run_pipeline

    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc1 = await run_pipeline("a.pdf", pdf_bytes, "application/pdf", db_session)
    doc2 = await run_pipeline("b.pdf", pdf_bytes, "application/pdf", db_session)

    assert doc1.document_id == doc2.document_id
