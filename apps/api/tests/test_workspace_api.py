"""Phase 14.2 — workspace resolution dependency + /workspaces CRUD."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_pipeline.api.main import app
from invoice_pipeline.db.models import AuditLog, Base, Document, Invoice, InvoiceField, Vendor, Workspace
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
async def test_create_guest_workspace(client: AsyncClient) -> None:
    res = await client.post("/workspaces")
    assert res.status_code == 201
    data = res.json()
    assert data["workspace_type"] == "guest"
    assert data["status"] == "active"
    assert data["expires_at"] is not None


@pytest.mark.asyncio
async def test_get_my_workspace_resolves_via_guest_header(client: AsyncClient) -> None:
    created = (await client.post("/workspaces")).json()
    res = await client.get("/workspaces/me", headers={"X-Workspace-Id": created["id"]})
    assert res.status_code == 200
    assert res.json()["id"] == created["id"]


@pytest.mark.asyncio
async def test_get_my_workspace_requires_auth(client: AsyncClient) -> None:
    res = await client.get("/workspaces/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_workspace_requires_header(client: AsyncClient) -> None:
    created = (await client.post("/workspaces")).json()
    res = await client.get(f"/workspaces/{created['id']}")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_workspace_self_only(client: AsyncClient) -> None:
    created = (await client.post("/workspaces")).json()
    other = (await client.post("/workspaces")).json()

    res = await client.get(
        f"/workspaces/{other['id']}", headers={"X-Workspace-Id": created["id"]}
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_workspace_expired_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ws = Workspace(
        workspace_type="guest",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(ws)
    await db_session.commit()

    res = await client.get(f"/workspaces/{ws.id}", headers={"X-Workspace-Id": ws.id})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_delete_workspace_purges_everything(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ws = Workspace(workspace_type="guest", expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    db_session.add(ws)
    await db_session.flush()

    vendor = Vendor(id="v1", workspace_id=ws.id, canonical_name="Acme")
    doc = Document(
        id="d" * 64,
        workspace_id=ws.id,
        filename="x.pdf",
        mime_type="application/pdf",
        file_size_bytes=1,
    )
    db_session.add_all([vendor, doc])
    await db_session.flush()

    invoice = Invoice(id="inv-1", workspace_id=ws.id, document_id=doc.id, vendor_id=vendor.id)
    db_session.add(invoice)
    await db_session.flush()

    field = InvoiceField(invoice_id=invoice.id, field_name="total_amount")
    audit = AuditLog(workspace_id=ws.id, document_id=doc.id, stage="test", action="test")
    db_session.add_all([field, audit])
    await db_session.commit()

    fake_file = upload_dir(ws.id) / doc.id
    fake_file.write_bytes(b"fake pdf bytes")
    assert fake_file.exists()

    res = await client.delete(f"/workspaces/{ws.id}", headers={"X-Workspace-Id": ws.id})
    assert res.status_code == 204

    assert (await db_session.execute(select(Workspace).where(Workspace.id == ws.id))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Vendor).where(Vendor.id == "v1"))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Document).where(Document.id == doc.id))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Invoice).where(Invoice.id == "inv-1"))).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(InvoiceField).where(InvoiceField.invoice_id == "inv-1"))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(AuditLog).where(AuditLog.document_id == doc.id))
    ).scalar_one_or_none() is None
    assert not fake_file.exists()
    assert not upload_dir(ws.id).exists() or list(upload_dir(ws.id).iterdir()) == []


@pytest.mark.asyncio
async def test_delete_workspace_self_only(client: AsyncClient) -> None:
    created = (await client.post("/workspaces")).json()
    other = (await client.post("/workspaces")).json()

    res = await client.delete(
        f"/workspaces/{other['id']}", headers={"X-Workspace-Id": created["id"]}
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_workspace_provider_preference(client: AsyncClient) -> None:
    created = (await client.post("/workspaces")).json()
    ws_id = created["id"]

    res = await client.get(f"/workspaces/{ws_id}/provider-preference", headers={"X-Workspace-Id": ws_id})
    assert res.status_code == 200
    assert res.json() == {"has_saved_api_key": False}


@pytest.mark.asyncio
async def test_update_workspace_provider_preference(client: AsyncClient) -> None:
    created = (await client.post("/workspaces")).json()
    ws_id = created["id"]

    res = await client.patch(
        f"/workspaces/{ws_id}/provider-preference", 
        json={"preference": {"provider": "openai"}},
        headers={"X-Workspace-Id": ws_id}
    )
    assert res.status_code == 200
    assert res.json()["provider"] == "openai"
    assert res.json()["has_saved_api_key"] is False

    res = await client.get(f"/workspaces/{ws_id}/provider-preference", headers={"X-Workspace-Id": ws_id})
    assert res.json()["provider"] == "openai"
    assert res.json()["has_saved_api_key"] is False

    # Reject invalid provider
    res = await client.patch(
        f"/workspaces/{ws_id}/provider-preference", 
        json={"provider": "invalid"},
        headers={"X-Workspace-Id": ws_id}
    )
    assert res.status_code == 422
