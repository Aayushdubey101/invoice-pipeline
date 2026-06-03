"""
Phase 4 tests — OCR + Email paths.
OCR engines mocked (heavy deps not installed in dev).
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from invoice_pipeline.db.models import Base
from invoice_pipeline.llm.base import ExtractionMeta
from invoice_pipeline.schemas import DocumentStatus, DocumentType, FieldValue, Invoice

FIXTURES = Path(__file__).parent / "fixtures"


# ── Shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _mock_invoice() -> Invoice:
    return Invoice(
        invoice_number=FieldValue(value="INV-2024-001", confidence=0.95),
        total_amount=FieldValue(value="1100.00", confidence=0.96),
        currency=FieldValue(value="USD", confidence=0.99),
        vendor_name=FieldValue(value="Acme Corp", confidence=0.92),
    )


@pytest.fixture
def mock_llm():
    meta = ExtractionMeta("openai", "gpt-4o-mini", 200.0, 300, 100, 0.0)
    provider = AsyncMock()
    provider.extract = AsyncMock(return_value=(_mock_invoice(), meta))
    with patch("invoice_pipeline.stages.field_extract.get_provider", return_value=provider):
        yield provider


# ── classify routing ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_scanned_pdf():
    from invoice_pipeline.stages.classify import classify
    from invoice_pipeline.stages.ingest import ingest

    pdf = (FIXTURES / "scanned_invoice.pdf").read_bytes()
    doc = await ingest("scanned.pdf", pdf, "application/pdf")
    doc = await classify(doc)

    assert doc.doc_type == DocumentType.SCANNED_PDF


@pytest.mark.asyncio
async def test_classify_image_png():
    from invoice_pipeline.stages.classify import classify
    from invoice_pipeline.stages.ingest import ingest

    png = (FIXTURES / "invoice_image.png").read_bytes()
    doc = await ingest("invoice.png", png, "image/png")
    doc = await classify(doc)

    assert doc.doc_type == DocumentType.IMAGE


@pytest.mark.asyncio
async def test_classify_email():
    from invoice_pipeline.stages.classify import classify
    from invoice_pipeline.stages.ingest import ingest

    eml = (FIXTURES / "invoice_email.eml").read_bytes()
    doc = await ingest("invoice.eml", eml, "message/rfc822")
    doc = await classify(doc)

    assert doc.doc_type == DocumentType.EMAIL


# ── OCR stage ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ocr_fallback_calls_engine():
    from invoice_pipeline.schemas import Page
    from invoice_pipeline.stages.ingest import ingest
    from invoice_pipeline.stages.ocr_fallback import ocr_fallback

    png = (FIXTURES / "invoice_image.png").read_bytes()
    doc = await ingest("invoice.png", png, "image/png")

    mock_engine = AsyncMock()
    mock_engine.extract_pages = AsyncMock(
        return_value=[Page(page_num=0, text="Invoice Number: INV-OCR-001\nTotal: $500.00")]
    )
    with patch("invoice_pipeline.stages.ocr_fallback._load_engine", return_value=mock_engine):
        result = await ocr_fallback(doc)

    assert result.raw_text != ""
    assert "INV-OCR-001" in result.raw_text
    assert mock_engine.extract_pages.called


@pytest.mark.asyncio
async def test_ocr_fallback_engine_error_does_not_raise():
    from invoice_pipeline.stages.ingest import ingest
    from invoice_pipeline.stages.ocr_fallback import ocr_fallback

    png = (FIXTURES / "invoice_image.png").read_bytes()
    doc = await ingest("invoice.png", png, "image/png")

    mock_engine = AsyncMock()
    mock_engine.extract_pages = AsyncMock(side_effect=RuntimeError("OCR engine crash"))
    with patch("invoice_pipeline.stages.ocr_fallback._load_engine", return_value=mock_engine):
        result = await ocr_fallback(doc)

    assert len(result.errors) == 1
    assert result.errors[0].stage == "ocr_fallback"


def test_ocr_engine_loads_tesseract_when_configured():
    from invoice_pipeline.config import OCREngineName
    from invoice_pipeline.ocr.tesseract import TesseractEngine
    from invoice_pipeline.stages.ocr_fallback import _load_engine

    with patch("invoice_pipeline.stages.ocr_fallback.settings") as s:
        s.OCR_ENGINE = OCREngineName.TESSERACT
        engine = _load_engine()
        assert isinstance(engine, TesseractEngine)


def test_ocr_engine_paddle_import_error_falls_back_to_tesseract():
    from invoice_pipeline.config import OCREngineName
    from invoice_pipeline.ocr.tesseract import TesseractEngine
    from invoice_pipeline.stages.ocr_fallback import _load_engine

    with patch("invoice_pipeline.stages.ocr_fallback.settings") as s:
        s.OCR_ENGINE = OCREngineName.PADDLEOCR
        # Simulate paddle module's internal import failing at instantiation time
        with patch(
            "invoice_pipeline.ocr.paddle.PaddleOCREngine",
            side_effect=ImportError("paddleocr not installed"),
        ):
            engine = _load_engine()
            assert isinstance(engine, TesseractEngine)


# ── Email extraction ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_email_text_extract():
    from invoice_pipeline.stages.ingest import ingest
    from invoice_pipeline.stages.text_extract import text_extract

    eml = (FIXTURES / "invoice_email.eml").read_bytes()
    doc = await ingest("invoice.eml", eml, "message/rfc822")
    doc = doc.model_copy(
        update={
            "doc_type": __import__(
                "invoice_pipeline.schemas", fromlist=["DocumentType"]
            ).DocumentType.EMAIL
        }
    )
    doc = await text_extract(doc)

    assert "INV-2024-002" in doc.raw_text
    assert len(doc.pages) > 0


@pytest.mark.asyncio
async def test_email_stdlib_fallback():
    from invoice_pipeline.stages.text_extract import _extract_email_stdlib

    eml = (FIXTURES / "invoice_email.eml").read_bytes()
    pages = _extract_email_stdlib(eml)

    assert len(pages) == 1
    assert "INV-2024-002" in pages[0].text
    assert "Acme Corp" in pages[0].text


# ── Full pipeline through OCR path ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_image_via_ocr(mock_llm, db_session):
    from invoice_pipeline.pipeline import run_pipeline
    from invoice_pipeline.schemas import Page

    png = (FIXTURES / "invoice_image.png").read_bytes()
    mock_engine = AsyncMock()
    mock_engine.extract_pages = AsyncMock(
        return_value=[Page(page_num=0, text="Invoice Total: $1100.00 USD Vendor: Acme Corp")]
    )
    with patch("invoice_pipeline.stages.ocr_fallback._load_engine", return_value=mock_engine):
        doc = await run_pipeline("invoice.png", png, "image/png", db_session)

    assert doc.document_id is not None
    assert doc.status in (DocumentStatus.COMPLETE, DocumentStatus.NEEDS_REVIEW)


@pytest.mark.asyncio
async def test_pipeline_email(mock_llm, db_session):
    from invoice_pipeline.pipeline import run_pipeline

    eml = (FIXTURES / "invoice_email.eml").read_bytes()
    doc = await run_pipeline("invoice.eml", eml, "message/rfc822", db_session)

    assert doc.document_id is not None
    assert doc.extracted is not None
