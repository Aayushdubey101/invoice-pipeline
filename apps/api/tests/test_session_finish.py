"""Phase 14.6 — Finish Session: PDF+Excel+JSON bundle, then full workspace purge."""

import io
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import openpyxl
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_pipeline.api.main import app
from invoice_pipeline.db.models import AuditLog, Base, Document, Invoice, LineItem, Vendor, Workspace
from invoice_pipeline.db.session import get_session
from invoice_pipeline.utils.storage import upload_dir


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


@pytest.mark.asyncio
async def test_finish_session_returns_bundle_and_purges_everything(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ws = Workspace(workspace_type="guest", expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    db_session.add(ws)
    await db_session.flush()

    vendor = Vendor(id="v1", workspace_id=ws.id, canonical_name="Acme Corp")
    doc = Document(
        id="d" * 64,
        workspace_id=ws.id,
        filename="invoice.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        status="complete",
        errors=[],
    )
    db_session.add_all([vendor, doc])
    await db_session.flush()

    inv = Invoice(
        id="inv-1",
        workspace_id=ws.id,
        document_id=doc.id,
        vendor_id=vendor.id,
        invoice_number="INV-FINISH-1",
        invoice_date="2024-01-15",
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("10.00"),
        total_amount=Decimal("110.00"),
        currency="USD",
        needs_review=False,
        raw_extraction={},
    )
    db_session.add(inv)
    await db_session.flush()

    db_session.add(
        LineItem(invoice_id=inv.id, position=0, description_raw="Widget", quantity_raw="1", total_raw="100.00")
    )
    db_session.add(
        AuditLog(workspace_id=ws.id, document_id=doc.id, stage="persist", action="upsert")
    )
    await db_session.commit()

    fake_file = upload_dir(ws.id) / doc.id
    fake_file.write_bytes(b"fake pdf bytes")

    res = await client.post("/session/finish", headers={"X-Workspace-Id": ws.id})
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        names = set(zf.namelist())
        assert names == {"invoices.xlsx", "invoices.pdf", "invoices.json"}

        wb = openpyxl.load_workbook(io.BytesIO(zf.read("invoices.xlsx")))
        ws1 = wb["Invoices"]
        assert ws1[2][0].value == "INV-FINISH-1"

        pdf_bytes = zf.read("invoices.pdf")
        assert pdf_bytes.startswith(b"%PDF")

        import json

        payload = json.loads(zf.read("invoices.json"))
        assert len(payload) == 1
        assert payload[0]["invoice_number"] == "INV-FINISH-1"

    # Everything belonging to the workspace is gone — including AuditLog
    # (guest zero-retention overrides the "immutable audit trail" invariant).
    assert (await db_session.execute(select(Workspace).where(Workspace.id == ws.id))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Vendor).where(Vendor.id == "v1"))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Document).where(Document.id == doc.id))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Invoice).where(Invoice.id == "inv-1"))).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(AuditLog).where(AuditLog.document_id == doc.id))
    ).scalar_one_or_none() is None
    assert not fake_file.exists()
    assert not upload_dir(ws.id).exists() or list(upload_dir(ws.id).iterdir()) == []


@pytest.mark.asyncio
async def test_finish_session_requires_workspace_header(client: AsyncClient) -> None:
    res = await client.post("/session/finish")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_finish_session_empty_workspace_still_returns_bundle(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ws = Workspace(workspace_type="guest", expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    db_session.add(ws)
    await db_session.commit()

    res = await client.post("/session/finish", headers={"X-Workspace-Id": ws.id})
    assert res.status_code == 200

    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        import json

        payload = json.loads(zf.read("invoices.json"))
        assert payload == []

    assert (await db_session.execute(select(Workspace).where(Workspace.id == ws.id))).scalar_one_or_none() is None
