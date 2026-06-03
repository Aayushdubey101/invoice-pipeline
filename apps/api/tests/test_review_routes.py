"""
Phase 6 tests — review, vendor, and invoice API routes.
Uses SQLite in-memory DB + FastAPI dependency override for get_session.
"""

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_pipeline.api.main import app
from invoice_pipeline.db.models import AuditLog, Base, Document, Invoice, InvoiceField, Vendor
from invoice_pipeline.db.session import get_session

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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Seed helpers ──────────────────────────────────────────────────────────────


async def seed_vendor(session: AsyncSession, **kwargs) -> Vendor:
    v = Vendor(
        id=kwargs.get("id", "v-001"),
        canonical_name=kwargs.get("canonical_name", "Acme Corp"),
        aliases=kwargs.get("aliases", ["ACME"]),
        status=kwargs.get("status", "active"),
    )
    session.add(v)
    await session.commit()
    return v


async def seed_doc_and_invoice(
    session: AsyncSession,
    vendor_id: str | None = None,
    needs_review: bool = True,
) -> tuple[Document, Invoice]:
    doc = Document(
        id="d" * 64,
        filename="invoice.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        doc_type="text_pdf",
        status="needs_review" if needs_review else "complete",
        errors=[],
    )
    session.add(doc)
    await session.flush()

    inv = Invoice(
        id="inv-001",
        document_id=doc.id,
        vendor_id=vendor_id,
        invoice_number="INV-001",
        invoice_date="2024-01-15",
        total_amount=Decimal("1100.00"),
        currency="USD",
        needs_review=needs_review,
        review_reasons=["low_confidence: invoice_date"] if needs_review else [],
        raw_extraction={},
    )
    session.add(inv)
    await session.commit()
    return doc, inv


async def seed_field(session: AsyncSession, invoice_id: str, **kwargs) -> InvoiceField:
    f = InvoiceField(
        id=kwargs.get("id", "field-001"),
        invoice_id=invoice_id,
        field_name=kwargs.get("field_name", "invoice_number"),
        raw_value=kwargs.get("raw_value", "INV-001"),
        canonical_value=kwargs.get("canonical_value", "INV-001"),
        confidence=kwargs.get("confidence", 0.95),
        evidence=kwargs.get("evidence", "INV-001"),
        needs_review=kwargs.get("needs_review", False),
        reviewed=kwargs.get("reviewed", False),
    )
    session.add(f)
    await session.commit()
    return f


# ── Review queue ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_queue_empty(client: AsyncClient) -> None:
    res = await client.get("/review/queue")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_review_queue_returns_pending_items(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    vendor = await seed_vendor(db_session)
    await seed_doc_and_invoice(db_session, vendor_id=vendor.id, needs_review=True)

    res = await client.get("/review/queue")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["id"] == "inv-001"
    assert item["vendor_name"] == "Acme Corp"
    assert item["needs_review"] is True


@pytest.mark.asyncio
async def test_review_queue_excludes_non_review_invoices(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await seed_doc_and_invoice(db_session, needs_review=False)

    res = await client.get("/review/queue")
    assert res.status_code == 200
    assert res.json()["total"] == 0


# ── Approve ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_invoice(client: AsyncClient, db_session: AsyncSession) -> None:
    doc, inv = await seed_doc_and_invoice(db_session, needs_review=True)
    await seed_field(db_session, inv.id)

    res = await client.post(f"/review/{inv.id}/approve")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "approved"

    await db_session.refresh(inv)
    await db_session.refresh(doc)
    assert inv.needs_review is False
    assert doc.status == "complete"


@pytest.mark.asyncio
async def test_approve_invoice_not_found(client: AsyncClient) -> None:
    res = await client.post("/review/nonexistent/approve")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_approve_writes_audit_log(client: AsyncClient, db_session: AsyncSession) -> None:
    from sqlalchemy import select

    doc, inv = await seed_doc_and_invoice(db_session, needs_review=True)

    await client.post(f"/review/{inv.id}/approve")

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.document_id == doc.id, AuditLog.action == "approved")
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.stage == "review"


# ── Reject ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reject_invoice(client: AsyncClient, db_session: AsyncSession) -> None:
    doc, inv = await seed_doc_and_invoice(db_session, needs_review=True)

    res = await client.post(f"/review/{inv.id}/reject")
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"

    await db_session.refresh(doc)
    assert doc.status == "failed"


@pytest.mark.asyncio
async def test_reject_invoice_not_found(client: AsyncClient) -> None:
    res = await client.post("/review/nonexistent/reject")
    assert res.status_code == 404


# ── Field update ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_field(client: AsyncClient, db_session: AsyncSession) -> None:
    doc, inv = await seed_doc_and_invoice(db_session)
    field = await seed_field(db_session, inv.id)

    res = await client.patch(
        f"/review/{inv.id}/field/{field.id}",
        json={"reviewed_value": "INV-CORRECTED"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["reviewed_value"] == "INV-CORRECTED"

    await db_session.refresh(field)
    assert field.reviewed is True
    assert field.reviewed_value == "INV-CORRECTED"


@pytest.mark.asyncio
async def test_update_field_null_value(client: AsyncClient, db_session: AsyncSession) -> None:
    doc, inv = await seed_doc_and_invoice(db_session)
    field = await seed_field(db_session, inv.id)

    res = await client.patch(
        f"/review/{inv.id}/field/{field.id}",
        json={"reviewed_value": None},
    )
    assert res.status_code == 200
    assert res.json()["reviewed_value"] is None


@pytest.mark.asyncio
async def test_update_field_not_found(client: AsyncClient, db_session: AsyncSession) -> None:
    doc, inv = await seed_doc_and_invoice(db_session)

    res = await client.patch(
        f"/review/{inv.id}/field/nonexistent",
        json={"reviewed_value": "x"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_update_field_wrong_invoice(client: AsyncClient, db_session: AsyncSession) -> None:
    doc, inv = await seed_doc_and_invoice(db_session)
    field = await seed_field(db_session, inv.id)

    res = await client.patch(
        f"/review/wrong-invoice-id/field/{field.id}",
        json={"reviewed_value": "x"},
    )
    assert res.status_code == 404


# ── Vendors ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_vendors_empty(client: AsyncClient) -> None:
    res = await client.get("/vendors/")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_vendors(client: AsyncClient, db_session: AsyncSession) -> None:
    await seed_vendor(db_session, id="v1", canonical_name="Acme Corp", aliases=["ACME"])
    await seed_vendor(db_session, id="v2", canonical_name="Beta Inc", aliases=[])

    res = await client.get("/vendors/")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    names = [v["canonical_name"] for v in data["items"]]
    assert "Acme Corp" in names
    assert "Beta Inc" in names


@pytest.mark.asyncio
async def test_update_vendor_canonical_name(client: AsyncClient, db_session: AsyncSession) -> None:
    vendor = await seed_vendor(db_session)

    res = await client.patch(f"/vendors/{vendor.id}", json={"canonical_name": "ACME Corporation"})
    assert res.status_code == 200
    data = res.json()
    assert data["canonical_name"] == "ACME Corporation"

    await db_session.refresh(vendor)
    assert vendor.canonical_name == "ACME Corporation"


@pytest.mark.asyncio
async def test_update_vendor_aliases(client: AsyncClient, db_session: AsyncSession) -> None:
    vendor = await seed_vendor(db_session)

    res = await client.patch(f"/vendors/{vendor.id}", json={"aliases": ["Acme", "ACME Corp"]})
    assert res.status_code == 200

    await db_session.refresh(vendor)
    assert vendor.aliases == ["Acme", "ACME Corp"]


@pytest.mark.asyncio
async def test_update_vendor_not_found(client: AsyncClient) -> None:
    res = await client.patch("/vendors/nonexistent", json={"canonical_name": "X"})
    assert res.status_code == 404


# ── Invoices ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_invoice(client: AsyncClient, db_session: AsyncSession) -> None:
    vendor = await seed_vendor(db_session)
    doc, inv = await seed_doc_and_invoice(db_session, vendor_id=vendor.id)
    await seed_field(db_session, inv.id)

    res = await client.get(f"/invoices/{inv.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == inv.id
    assert data["invoice_number"] == "INV-001"
    assert data["vendor_name"] == "Acme Corp"
    assert data["total_amount"] is not None
    assert float(data["total_amount"]) == pytest.approx(1100.0)
    assert len(data["fields"]) == 1
    assert data["fields"][0]["field_name"] == "invoice_number"


@pytest.mark.asyncio
async def test_get_invoice_not_found(client: AsyncClient) -> None:
    res = await client.get("/invoices/nonexistent")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_invoice_fields_have_confidence(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    doc, inv = await seed_doc_and_invoice(db_session)
    await seed_field(db_session, inv.id, confidence=0.72)

    res = await client.get(f"/invoices/{inv.id}")
    assert res.status_code == 200
    field = res.json()["fields"][0]
    assert abs(field["confidence"] - 0.72) < 0.01
