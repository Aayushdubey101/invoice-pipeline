"""Phase 14.7 — hourly guest-workspace cleanup job."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_pipeline.db.models import Base, Workspace
from invoice_pipeline.services.workspace_cleanup import run_cleanup


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


@pytest.fixture(autouse=True)
def patch_cleanup_session(db_engine):
    test_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    with patch("invoice_pipeline.services.workspace_cleanup.async_session_factory", test_factory):
        yield


@pytest.mark.asyncio
async def test_run_cleanup_purges_only_expired_guest_workspaces(db_session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    expired_1 = Workspace(workspace_type="guest", expires_at=now - timedelta(hours=2))
    expired_2 = Workspace(workspace_type="guest", expires_at=now - timedelta(minutes=1))
    active_guest = Workspace(workspace_type="guest", expires_at=now + timedelta(hours=1))
    authenticated = Workspace(workspace_type="authenticated", clerk_user_id="user_1", expires_at=None)
    db_session.add_all([expired_1, expired_2, active_guest, authenticated])
    await db_session.commit()

    expired_1_id, expired_2_id = expired_1.id, expired_2.id
    active_guest_id, authenticated_id = active_guest.id, authenticated.id

    await run_cleanup()

    remaining_ids = set((await db_session.execute(select(Workspace.id))).scalars().all())
    assert expired_1_id not in remaining_ids
    assert expired_2_id not in remaining_ids
    assert active_guest_id in remaining_ids
    assert authenticated_id in remaining_ids


@pytest.mark.asyncio
async def test_run_cleanup_is_noop_when_nothing_expired(db_session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    active_guest = Workspace(workspace_type="guest", expires_at=now + timedelta(hours=1))
    db_session.add(active_guest)
    await db_session.commit()
    active_guest_id = active_guest.id

    await run_cleanup()

    remaining_ids = set((await db_session.execute(select(Workspace.id))).scalars().all())
    assert active_guest_id in remaining_ids
