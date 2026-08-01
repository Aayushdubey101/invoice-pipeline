"""Phase 14.10 - test migration of guest workspace to authenticated workspace."""
from datetime import datetime, timedelta, timezone
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_pipeline.api.main import app
from invoice_pipeline.db.models import Base, Workspace, Document, Invoice, Batch
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
async def test_migrate_workspace_success(client: AsyncClient, db_session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    guest_ws = Workspace(workspace_type="guest", expires_at=now + timedelta(hours=1))
    auth_ws = Workspace(workspace_type="authenticated", clerk_user_id="user_migrate")
    db_session.add_all([guest_ws, auth_ws])
    await db_session.commit()
    guest_id = guest_ws.id
    auth_id = auth_ws.id

    batch = Batch(workspace_id=guest_id)
    doc = Document(id="doc-1", workspace_id=guest_id, filename="test.pdf", mime_type="application/pdf", file_size_bytes=100)
    inv = Invoice(workspace_id=guest_id, document_id=doc.id)
    db_session.add_all([batch, doc, inv])
    await db_session.commit()
    
    # create files
    gdir = upload_dir(guest_id)
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "test.pdf").write_text("hello")

    from unittest.mock import patch
    with patch("invoice_pipeline.api.deps.verify_clerk_token") as mock_verify:
        mock_verify.return_value = "user_migrate"
        resp = await client.post(
            "/workspaces/migrate",
            json={"guest_workspace_id": guest_id},
            headers={"Authorization": "Bearer mock_token"} # authenticated workspace
        )
    
    assert resp.status_code == 200
    assert resp.json()["migrated_to"] == auth_id

    # check db
    result = await db_session.execute(select(Workspace).where(Workspace.id == guest_id))
    assert result.scalar_one_or_none() is None

    result_doc = await db_session.execute(select(Document).where(Document.id == doc.id))
    assert result_doc.scalar_one().workspace_id == auth_id

    # check files
    adir = upload_dir(auth_id)
    assert (adir / "test.pdf").exists()
    assert not gdir.exists()

@pytest.mark.asyncio
async def test_migrate_workspace_unauthenticated(client: AsyncClient, db_session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    guest_ws1 = Workspace(workspace_type="guest", expires_at=now + timedelta(hours=1))
    guest_ws2 = Workspace(workspace_type="guest", expires_at=now + timedelta(hours=1))
    db_session.add_all([guest_ws1, guest_ws2])
    await db_session.commit()
    
    resp = await client.post(
        "/workspaces/migrate",
        json={"guest_workspace_id": guest_ws1.id},
        headers={"X-Workspace-Id": guest_ws2.id}
    )

    assert resp.status_code == 403

@pytest.mark.asyncio
async def test_migrate_workspace_expired(client: AsyncClient, db_session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    guest_ws = Workspace(workspace_type="guest", expires_at=now - timedelta(hours=1))
    auth_ws = Workspace(workspace_type="authenticated", clerk_user_id="user_x")
    db_session.add_all([guest_ws, auth_ws])
    await db_session.commit()
    
    from unittest.mock import patch
    with patch("invoice_pipeline.api.deps.verify_clerk_token") as mock_verify:
        mock_verify.return_value = "user_x"
        resp = await client.post(
            "/workspaces/migrate",
            json={"guest_workspace_id": guest_ws.id},
            headers={"Authorization": "Bearer mock_token"}
        )
    
    assert resp.status_code == 400
