"""Phase 14.3 — cross-workspace isolation regression tests.

Confirms the two behaviors this sub-phase exists to guarantee:
1. Two workspaces uploading byte-identical content get two distinct
   document_ids (the salted-hash fix — before this, they'd collide on the
   same Document PK and workspace B would silently see workspace A's data).
2. A workspace can never fetch another workspace's document (404, not a leak).
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock, patch

from invoice_pipeline.api.main import app
from invoice_pipeline.db.models import Base, Workspace
from invoice_pipeline.db.session import get_session
from invoice_pipeline.llm.base import ExtractionMeta
from invoice_pipeline.schemas import FieldValue
from invoice_pipeline.schemas import Invoice as ExtractedInvoice

FIXTURES = Path(__file__).parent / "fixtures"


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def mock_llm():
    invoice = ExtractedInvoice(
        invoice_number=FieldValue(value="INV-2024-001", confidence=0.95, evidence="INV-2024-001"),
        invoice_date=FieldValue(value="2024-01-15", confidence=0.9, evidence="2024-01-15"),
        vendor_name=FieldValue(value="Acme Corp", confidence=0.92, evidence="Acme Corp"),
        total_amount=FieldValue(value="1100.00", confidence=0.96, evidence="$1100.00"),
        currency=FieldValue(value="USD", confidence=0.99, evidence="USD"),
    )
    meta = ExtractionMeta(
        provider_name="openai", model_name="gpt-4o-mini", latency_ms=1.0,
        tokens_in=10, tokens_out=10, cost_estimate=0.0,
    )
    mock_provider = AsyncMock()
    mock_provider.extract = AsyncMock(return_value=(invoice, meta))
    with patch("invoice_pipeline.llm.factory._provider_instance", mock_provider):
        with patch("invoice_pipeline.stages.field_extract.get_provider", return_value=mock_provider):
            yield mock_provider


async def _make_workspace(session: AsyncSession) -> Workspace:
    ws = Workspace(workspace_type="guest", expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    session.add(ws)
    await session.commit()
    return ws


@pytest.mark.asyncio
async def test_identical_bytes_across_workspaces_get_distinct_document_ids(
    client: AsyncClient, db_session: AsyncSession, mock_llm
) -> None:
    ws_a = await _make_workspace(db_session)
    ws_b = await _make_workspace(db_session)
    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()

    res_a = await client.post(
        "/documents/upload",
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
        headers={"X-Workspace-Id": ws_a.id},
    )
    res_b = await client.post(
        "/documents/upload",
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
        headers={"X-Workspace-Id": ws_b.id},
    )

    assert res_a.status_code == 202
    assert res_b.status_code == 202
    assert res_a.json()["document_id"] != res_b.json()["document_id"]


@pytest.mark.asyncio
async def test_cross_workspace_document_access_is_404_not_leak(
    client: AsyncClient, db_session: AsyncSession, mock_llm
) -> None:
    ws_a = await _make_workspace(db_session)
    ws_b = await _make_workspace(db_session)
    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()

    upload_res = await client.post(
        "/documents/upload",
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
        headers={"X-Workspace-Id": ws_a.id},
    )
    document_id = upload_res.json()["document_id"]

    # Owner can fetch it.
    own_res = await client.get(
        f"/documents/{document_id}", headers={"X-Workspace-Id": ws_a.id}
    )
    assert own_res.status_code == 200

    # A different workspace gets 404, not workspace A's data.
    other_res = await client.get(
        f"/documents/{document_id}", headers={"X-Workspace-Id": ws_b.id}
    )
    assert other_res.status_code == 404

    other_file_res = await client.get(
        f"/documents/{document_id}/file", headers={"X-Workspace-Id": ws_b.id}
    )
    assert other_file_res.status_code == 404


async def _seed_full_invoice(session: AsyncSession, workspace_id: str) -> None:
    """A vendor + document + invoice (needing review) + field, all in one workspace."""
    from invoice_pipeline.db.models import Document, Invoice, InvoiceField, Vendor

    vendor = Vendor(id=f"v-{workspace_id}", workspace_id=workspace_id, canonical_name="Acme Corp", aliases=[])
    session.add(vendor)
    doc = Document(
        id=f"{workspace_id[:8]}{'0' * 56}",
        workspace_id=workspace_id,
        filename="invoice.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        status="needs_review",
        errors=[],
    )
    session.add(doc)
    await session.flush()
    inv = Invoice(
        id=f"inv-{workspace_id}",
        workspace_id=workspace_id,
        document_id=doc.id,
        vendor_id=vendor.id,
        invoice_number="INV-ISO",
        needs_review=True,
        raw_extraction={},
    )
    session.add(inv)
    await session.flush()
    session.add(
        InvoiceField(invoice_id=inv.id, field_name="invoice_number", raw_value="INV-ISO")
    )
    await session.commit()


@pytest.mark.asyncio
async def test_vendors_list_is_workspace_scoped(client: AsyncClient, db_session: AsyncSession) -> None:
    ws_a = await _make_workspace(db_session)
    ws_b = await _make_workspace(db_session)
    await _seed_full_invoice(db_session, ws_a.id)

    res_a = await client.get("/vendors/", headers={"X-Workspace-Id": ws_a.id})
    assert res_a.json()["total"] == 1

    res_b = await client.get("/vendors/", headers={"X-Workspace-Id": ws_b.id})
    assert res_b.json()["total"] == 0


@pytest.mark.asyncio
async def test_review_queue_is_workspace_scoped(client: AsyncClient, db_session: AsyncSession) -> None:
    ws_a = await _make_workspace(db_session)
    ws_b = await _make_workspace(db_session)
    await _seed_full_invoice(db_session, ws_a.id)

    res_a = await client.get("/review/queue", headers={"X-Workspace-Id": ws_a.id})
    assert res_a.json()["total"] == 1

    res_b = await client.get("/review/queue", headers={"X-Workspace-Id": ws_b.id})
    assert res_b.json()["total"] == 0


@pytest.mark.asyncio
async def test_dashboard_stats_is_workspace_scoped(client: AsyncClient, db_session: AsyncSession) -> None:
    ws_a = await _make_workspace(db_session)
    ws_b = await _make_workspace(db_session)
    await _seed_full_invoice(db_session, ws_a.id)

    res_a = await client.get("/dashboard/stats", headers={"X-Workspace-Id": ws_a.id})
    assert res_a.json()["totals"]["invoices"] == 1
    assert res_a.json()["totals"]["storage_usage_bytes"] == 10
    assert res_a.json()["provider_preference"] is None

    res_b = await client.get("/dashboard/stats", headers={"X-Workspace-Id": ws_b.id})
    assert res_b.json()["totals"]["invoices"] == 0
    assert res_b.json()["totals"]["storage_usage_bytes"] == 0
    assert res_b.json()["provider_preference"] is None


@pytest.mark.asyncio
async def test_export_history_is_workspace_scoped(client: AsyncClient, db_session: AsyncSession) -> None:
    ws_a = await _make_workspace(db_session)
    ws_b = await _make_workspace(db_session)
    await _seed_full_invoice(db_session, ws_a.id)

    await client.get("/export/excel", headers={"X-Workspace-Id": ws_a.id})

    res_a = await client.get("/export/history", headers={"X-Workspace-Id": ws_a.id})
    assert len(res_a.json()["exports"]) == 1

    res_b = await client.get("/export/history", headers={"X-Workspace-Id": ws_b.id})
    assert len(res_b.json()["exports"]) == 0
