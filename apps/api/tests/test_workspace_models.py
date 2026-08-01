"""Phase 14.1 — Workspace table + workspace_id columns (schema-only sub-phase).

Confirms: the new Workspace table + workspace_id FK columns create cleanly via
Base.metadata.create_all (the sqlite in-memory pattern every other test file
uses), Workspace CRUD works at the ORM level, and every workspace-scoped table
accepts an explicit workspace_id as well as falling back to LEGACY_WORKSPACE_ID
when omitted (the bridge that keeps pre-14.3/14.4 code, which doesn't thread a
real workspace_id yet, from hitting a NOT NULL constraint).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_pipeline.db.models import (
    LEGACY_WORKSPACE_ID,
    AuditLog,
    Base,
    Batch,
    Document,
    ExportHistory,
    Invoice,
    ReviewerFeedback,
    Vendor,
    VendorTemplate,
    Workspace,
)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_workspace_crud(db_session: AsyncSession) -> None:
    ws = Workspace(
        workspace_type="guest",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(ws)
    await db_session.commit()

    fetched = (await db_session.execute(select(Workspace).where(Workspace.id == ws.id))).scalar_one()
    assert fetched.workspace_type == "guest"
    assert fetched.status == "active"
    assert fetched.clerk_user_id is None
    assert fetched.provider_preference is None
    assert fetched.expires_at is not None


@pytest.mark.asyncio
async def test_authenticated_workspace_has_no_expiry_by_default(db_session: AsyncSession) -> None:
    ws = Workspace(workspace_type="authenticated", clerk_user_id="user_abc123")
    db_session.add(ws)
    await db_session.commit()

    fetched = (await db_session.execute(select(Workspace).where(Workspace.id == ws.id))).scalar_one()
    assert fetched.expires_at is None
    assert fetched.clerk_user_id == "user_abc123"


@pytest.mark.asyncio
async def test_scoped_tables_accept_explicit_workspace_id(db_session: AsyncSession) -> None:
    ws = Workspace(workspace_type="guest")
    db_session.add(ws)
    await db_session.flush()

    doc = Document(
        id="d" * 64,
        workspace_id=ws.id,
        filename="invoice.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
    )
    vendor = Vendor(workspace_id=ws.id, canonical_name="Acme")
    batch = Batch(workspace_id=ws.id, name="My Project")
    db_session.add_all([doc, vendor, batch])
    await db_session.commit()

    for row in (doc, vendor, batch):
        await db_session.refresh(row)
        assert row.workspace_id == ws.id

    assert batch.is_archived is False
    assert batch.archived_at is None


@pytest.mark.asyncio
async def test_scoped_tables_fall_back_to_legacy_workspace(db_session: AsyncSession) -> None:
    """Code that hasn't been threaded with a real workspace_id yet (everything
    before sub-phase 14.3/14.4) must still be able to insert rows."""
    doc = Document(id="e" * 64, filename="x.pdf", mime_type="application/pdf", file_size_bytes=1)
    vendor = Vendor(id="legacy-vendor-1", canonical_name="No Workspace Given")
    invoice = Invoice(document_id=doc.id)
    template = VendorTemplate(vendor_id=vendor.id, fingerprint="x")
    audit = AuditLog(document_id=doc.id, stage="test", action="test")
    feedback = ReviewerFeedback(document_id=doc.id, field_type="total_amount")
    batch = Batch()
    export = ExportHistory(export_type="single", filename="x.xlsx")

    db_session.add_all([doc, vendor, invoice, template, audit, feedback, batch, export])
    await db_session.commit()

    for row in (doc, vendor, invoice, template, audit, feedback, batch, export):
        await db_session.refresh(row)
        assert row.workspace_id == LEGACY_WORKSPACE_ID
