import hashlib
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_pipeline.api.deps import db
from invoice_pipeline.api.main import app, lifespan
from invoice_pipeline.api.routes.documents import get_document, get_document_file
from invoice_pipeline.api.routes.review import (
    FieldUpdateBody,
    approve_invoice,
    reject_invoice,
    review_queue,
    update_field,
)
from invoice_pipeline.canonicalizers.tax_ids import validate_tax_id
from invoice_pipeline.canonicalizers.vendors import match_or_create_vendor
from invoice_pipeline.db.models import Base, Document, Invoice, InvoiceField, Vendor
from invoice_pipeline.db.session import get_session
from invoice_pipeline.llm.base import NoLLMProviderConfigured


# ── Dynamic Route for testing exception handling ──────────────────────────────
@app.get("/test-error-endpoint")
async def trigger_error():
    raise ValueError("Something went wrong in the test")


# ── DB fixture ────────────────────────────────────────────────────────────────


@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ── 1. deps.py ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deps_db():
    mock_session = AsyncMock(spec=AsyncSession)
    async for sess in db(mock_session):
        assert sess == mock_session


# ── 2. main.py ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generic_exception_handler(client: AsyncClient):
    response = await client.get("/test-error-endpoint")
    assert response.status_code == 500
    data = response.json()
    assert data["title"] == "Internal Server Error"
    assert data["detail"] == "An unexpected error occurred."


@pytest.mark.asyncio
async def test_metrics_endpoint(client: AsyncClient):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")


@pytest.mark.asyncio
async def test_lifespan_llm_not_configured():
    with patch(
        "invoice_pipeline.api.main.create_provider",
        side_effect=NoLLMProviderConfigured("No provider"),
    ):
        async with lifespan(app):
            assert app.state.llm_provider is None
            assert app.state.llm_status["provider"] == "none"


@pytest.mark.asyncio
async def test_llm_status_exception_fallback(client: AsyncClient):
    with patch("invoice_pipeline.llm.factory.get_provider", side_effect=Exception("Failed")):
        response = await client.get("/llm/status")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_llm_status_lm_studio(client: AsyncClient):
    mock_provider = MagicMock()
    mock_provider.provider_name = "lm_studio"
    mock_provider._model = "test-model"
    mock_provider._base_url = "http://lm-studio:1234"

    with (
        patch("invoice_pipeline.llm.factory.get_provider", return_value=mock_provider),
        patch(
            "invoice_pipeline.llm.lm_studio._get_active_models",
            new_callable=AsyncMock,
            return_value=["lm-model-1"],
        ),
    ):
        response = await client.get("/llm/status")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "lm_studio"


# ── 3. documents.py ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_document_404(client: AsyncClient):
    response = await client.get("/documents/non-existent-id")
    assert response.status_code == 404
    assert "Document not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_document_file_404(client: AsyncClient):
    response = await client.get("/documents/non-existent-id/file")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_document_file_missing_on_disk(client: AsyncClient, db_session: AsyncSession):
    doc_id = "test-doc-missing-disk"
    doc = Document(
        id=doc_id,
        filename="missing.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        doc_type="text_pdf",
        status="complete",
    )
    db_session.add(doc)
    await db_session.commit()

    response = await client.get(f"/documents/{doc_id}/file")
    assert response.status_code == 404
    assert "content not found on disk" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_document_file_success(client: AsyncClient, db_session: AsyncSession):
    doc_id = "test-doc-file-id"
    doc = Document(
        id=doc_id,
        filename="test.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        doc_type="text_pdf",
        status="complete",
    )
    db_session.add(doc)
    await db_session.commit()

    upload_dir = Path(__file__).resolve().parents[1] / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / doc_id
    file_path.write_bytes(b"dummy-file-content")

    try:
        response = await client.get(f"/documents/{doc_id}/file")
        assert response.status_code == 200
        assert response.read() == b"dummy-file-content"
    finally:
        if file_path.exists():
            file_path.unlink()


@pytest.mark.asyncio
async def test_upload_file_size_exceeded(client: AsyncClient):
    with patch(
        "starlette.datastructures.UploadFile.read",
        new_callable=AsyncMock,
        return_value=b"\x00" * (51 * 1024 * 1024),
    ):
        response = await client.post(
            "/documents/upload", files={"file": ("large.pdf", b"abc", "application/pdf")}
        )
        assert response.status_code == 413
        assert "exceeds 50 MB limit" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_existing_idempotent(client: AsyncClient, db_session: AsyncSession):
    file_bytes = b"existing-content-123"
    doc_id = hashlib.sha256(file_bytes).hexdigest()

    doc = Document(
        id=doc_id,
        filename="existing.pdf",
        mime_type="application/pdf",
        file_size_bytes=len(file_bytes),
        doc_type="text_pdf",
        status="complete",
        errors=[],
    )
    db_session.add(doc)
    await db_session.commit()

    response = await client.post(
        "/documents/upload", files={"file": ("existing.pdf", file_bytes, "application/pdf")}
    )
    assert response.status_code == 202
    data = response.json()
    assert data["document_id"] == doc_id
    assert data["status"] == "complete"


@pytest.mark.asyncio
async def test_upload_error_handling(client: AsyncClient):
    with patch(
        "invoice_pipeline.api.routes.documents.run_pipeline",
        side_effect=ValueError("Invalid file structure"),
    ):
        response = await client.post(
            "/documents/upload", files={"file": ("test.pdf", b"abc", "application/pdf")}
        )
        assert response.status_code == 422
        assert "Invalid file structure" in response.json()["detail"]


# ── 4. review.py ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_invoice_404(client: AsyncClient):
    response = await client.post("/review/non-existent-inv/approve")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reject_invoice_404(client: AsyncClient):
    response = await client.post("/review/non-existent-inv/reject")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_field_404(client: AsyncClient):
    response = await client.patch(
        "/review/non-existent-inv/field/non-existent-field", json={"reviewed_value": "test"}
    )
    assert response.status_code == 404


# ── 5. tax_ids.py ─────────────────────────────────────────────────────────────


def test_validate_tax_id_scenarios():
    # Empty cases
    assert validate_tax_id(None) is None
    assert validate_tax_id("") is None

    # Valid US EIN
    assert validate_tax_id("12-3456789") == "12-3456789"
    # Valid EU VAT
    assert validate_tax_id("DE123456789") == "DE123456789"
    # Fallback format
    assert validate_tax_id("XYZ-987-123") == "XYZ-987-123"


# ── 6. vendors.py ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vendor_embedding_match_success():
    mock_session = AsyncMock(spec=AsyncSession)
    vendor = Vendor(id="v1", canonical_name="Acme Corp", aliases=[], status="active")

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [vendor]
    mock_session.execute = AsyncMock(return_value=mock_result)

    with (
        patch("chromadb.HttpClient") as mock_chroma,
        patch("sentence_transformers.SentenceTransformer") as mock_model,
    ):
        mock_client = MagicMock()
        mock_chroma.return_value = mock_client
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_collection.query.return_value = {"distances": [[0.1]], "ids": [["v1"]]}

        mock_transformer = MagicMock()
        mock_model.return_value = mock_transformer
        mock_transformer.encode.return_value.tolist.return_value = [0.1, 0.2, 0.3]

        vendor_id, matched = await match_or_create_vendor("Beta Inc", mock_session)

        assert matched is True
        assert vendor_id == "v1"
        mock_collection.query.assert_called_once()


@pytest.mark.asyncio
async def test_vendor_match_empty_name():
    mock_session = AsyncMock(spec=AsyncSession)
    vendor_id, matched = await match_or_create_vendor("   ", mock_session)
    assert matched is False
    assert len(vendor_id) > 0


@pytest.mark.asyncio
async def test_upload_success_path(client: AsyncClient):
    from invoice_pipeline.schemas import DocumentStatus

    mock_doc = MagicMock()
    mock_doc.document_id = "mocked-upload-doc-id"
    mock_doc.status = DocumentStatus.COMPLETE
    mock_doc.errors = []

    with patch(
        "invoice_pipeline.api.routes.documents.run_pipeline",
        new_callable=AsyncMock,
        return_value=mock_doc,
    ):
        upload_dir = Path(__file__).resolve().parents[1] / "data" / "uploads"
        file_path = upload_dir / "mocked-upload-doc-id"
        try:
            response = await client.post(
                "/documents/upload", files={"file": ("test.pdf", b"pdf-bytes", "application/pdf")}
            )
            assert response.status_code == 202
            data = response.json()
            assert data["document_id"] == "mocked-upload-doc-id"
            assert data["status"] == "complete"
        finally:
            if file_path.exists():
                file_path.unlink()


@pytest.mark.asyncio
async def test_direct_document_routes(db_session: AsyncSession):
    doc_id = "test-doc-direct"
    doc = Document(
        id=doc_id,
        filename="direct.pdf",
        mime_type="application/pdf",
        file_size_bytes=200,
        doc_type="text_pdf",
        status="complete",
        errors=[],
    )
    db_session.add(doc)
    await db_session.flush()

    inv = Invoice(
        id="inv-doc-direct",
        document_id=doc_id,
        invoice_number="INV-DIRECT-1",
        invoice_date="2024-01-10",
        total_amount=Decimal("500.00"),
        currency="USD",
        needs_review=False,
        review_reasons=[],
        raw_extraction={},
    )
    db_session.add(inv)
    await db_session.commit()

    # Direct call get_document
    res_doc = await get_document(document_id=doc_id, session=db_session)
    assert res_doc["document_id"] == doc_id
    assert res_doc["invoice"]["invoice_number"] == "INV-DIRECT-1"

    # Direct call get_document_file success
    upload_dir = Path(__file__).resolve().parents[1] / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / doc_id
    file_path.write_bytes(b"direct-file-content")

    try:
        res_file = await get_document_file(document_id=doc_id, session=db_session)
        assert Path(res_file.path) == file_path
    finally:
        if file_path.exists():
            file_path.unlink()


@pytest.mark.asyncio
async def test_direct_review_routes(db_session: AsyncSession):
    doc = Document(
        id="d-review-direct",
        filename="invoice.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        doc_type="text_pdf",
        status="needs_review",
        errors=[],
    )
    db_session.add(doc)
    await db_session.flush()

    vendor = Vendor(
        id="v-review-direct",
        canonical_name="Acme Direct Review",
        aliases=[],
        status="active",
    )
    db_session.add(vendor)
    await db_session.flush()

    inv = Invoice(
        id="inv-review-direct",
        document_id=doc.id,
        vendor_id=vendor.id,
        invoice_number="INV-REV-DIRECT",
        invoice_date="2024-01-15",
        total_amount=Decimal("123.45"),
        currency="USD",
        needs_review=True,
        review_reasons=["low_confidence"],
        raw_extraction={},
    )
    db_session.add(inv)
    await db_session.flush()

    field = InvoiceField(
        id="field-review-direct",
        invoice_id=inv.id,
        field_name="total_amount",
        raw_value="123.45",
        canonical_value="123.45",
        confidence=0.5,
        evidence="$123.45",
        needs_review=True,
        reviewed=False,
    )
    db_session.add(field)
    await db_session.commit()

    res_queue = await review_queue(session=db_session)
    assert res_queue["total"] >= 1

    res_field = await update_field(
        invoice_id=inv.id,
        field_id=field.id,
        body=FieldUpdateBody(reviewed_value="123.50"),
        session=db_session,
    )
    assert res_field["field_id"] == field.id

    res_approve = await approve_invoice(invoice_id=inv.id, session=db_session)
    assert res_approve["status"] == "approved"

    doc_rej = Document(
        id="d-rej-direct",
        filename="invoice2.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        doc_type="text_pdf",
        status="needs_review",
        errors=[],
    )
    db_session.add(doc_rej)
    await db_session.flush()

    inv_rej = Invoice(
        id="inv-rej-direct",
        document_id=doc_rej.id,
        invoice_number="INV-REJ-DIRECT",
        needs_review=True,
        raw_extraction={},
    )
    db_session.add(inv_rej)
    await db_session.commit()

    res_reject = await reject_invoice(invoice_id=inv_rej.id, session=db_session)
    assert res_reject["status"] == "rejected"
