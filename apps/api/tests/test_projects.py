import pytest
from httpx import AsyncClient
from sqlalchemy import select

from invoice_pipeline.db.models import Batch, LEGACY_WORKSPACE_ID


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test_token"}


from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from invoice_pipeline.db.models import Base, Workspace, LEGACY_WORKSPACE_ID
from invoice_pipeline.api.main import app
from invoice_pipeline.db.session import get_session
from invoice_pipeline.api.deps import get_current_workspace
from httpx import ASGITransport

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

    async def override_get_current_workspace():
        ws = await db_session.get(Workspace, LEGACY_WORKSPACE_ID)
        if not ws:
            ws = Workspace(id=LEGACY_WORKSPACE_ID, workspace_type="authenticated")
            db_session.add(ws)
            await db_session.commit()
        return ws

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_workspace] = override_get_current_workspace
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient, db_session, auth_headers):
    payload = {"name": "Test Project"}
    resp = await client.post("/projects", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Project"
    assert "id" in data
    
    # Verify in DB
    result = await db_session.execute(select(Batch).filter_by(id=data["id"]))
    batch = result.scalar_one_or_none()
    assert batch is not None
    assert batch.name == "Test Project"
    assert not batch.is_archived


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient, db_session, auth_headers):
    # Create some projects directly
    b1 = Batch(workspace_id=LEGACY_WORKSPACE_ID, name="Active 1")
    b2 = Batch(workspace_id=LEGACY_WORKSPACE_ID, name="Active 2")
    b3 = Batch(workspace_id=LEGACY_WORKSPACE_ID, name="Archived 1", is_archived=True)
    db_session.add_all([b1, b2, b3])
    await db_session.commit()

    resp = await client.get("/projects", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    names = [p["name"] for p in data]
    assert "Active 1" in names
    assert "Active 2" in names
    assert "Archived 1" not in names  # Should exclude archived by default

    # Include archived
    resp = await client.get("/projects?include_archived=true", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    names = [p["name"] for p in data]
    assert "Archived 1" in names


@pytest.mark.asyncio
async def test_get_project_detail(client: AsyncClient, db_session, auth_headers):
    b1 = Batch(workspace_id=LEGACY_WORKSPACE_ID, name="Detail Project")
    db_session.add(b1)
    await db_session.commit()

    resp = await client.get(f"/projects/{b1.id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Project"
    assert data["id"] == b1.id


@pytest.mark.asyncio
async def test_rename_project(client: AsyncClient, db_session, auth_headers):
    b1 = Batch(workspace_id=LEGACY_WORKSPACE_ID, name="Old Name")
    db_session.add(b1)
    await db_session.commit()

    resp = await client.patch(f"/projects/{b1.id}", json={"name": "New Name"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"

    await db_session.refresh(b1)
    assert b1.name == "New Name"


@pytest.mark.asyncio
async def test_duplicate_project_empty_shell(client: AsyncClient, db_session, auth_headers):
    b1 = Batch(workspace_id=LEGACY_WORKSPACE_ID, name="Original")
    db_session.add(b1)
    await db_session.commit()

    resp = await client.post(f"/projects/{b1.id}/duplicate", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Original (Copy)"
    assert data["id"] != b1.id
    
    # Verify new shell exists in DB
    result = await db_session.execute(select(Batch).filter_by(id=data["id"]))
    new_batch = result.scalar_one_or_none()
    assert new_batch is not None
    assert new_batch.name == "Original (Copy)"
    assert new_batch.workspace_id == LEGACY_WORKSPACE_ID


@pytest.mark.asyncio
async def test_archive_unarchive_project(client: AsyncClient, db_session, auth_headers):
    b1 = Batch(workspace_id=LEGACY_WORKSPACE_ID, name="To Archive")
    db_session.add(b1)
    await db_session.commit()

    resp = await client.post(f"/projects/{b1.id}/archive", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_archived"] is True
    
    await db_session.refresh(b1)
    assert b1.is_archived is True
    assert b1.archived_at is not None

    resp = await client.post(f"/projects/{b1.id}/unarchive", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_archived"] is False
    
    await db_session.refresh(b1)
    assert b1.is_archived is False
    assert b1.archived_at is None


@pytest.mark.asyncio
async def test_delete_project_must_be_archived(client: AsyncClient, db_session, auth_headers):
    b1 = Batch(workspace_id=LEGACY_WORKSPACE_ID, name="Active Project")
    db_session.add(b1)
    await db_session.commit()

    # Try deleting while active
    resp = await client.delete(f"/projects/{b1.id}", headers=auth_headers)
    assert resp.status_code == 400
    assert "must be archived" in resp.json()["detail"]

    # Archive it
    b1.is_archived = True
    await db_session.commit()

    # Now delete should work
    resp = await client.delete(f"/projects/{b1.id}", headers=auth_headers)
    assert resp.status_code == 204

    # Verify deleted
    result = await db_session.execute(select(Batch).filter_by(id=b1.id))
    assert result.scalar_one_or_none() is None
