"""
Auto-approve regression test: when confidence_score.py marks needs_review=False,
persist() must write the invoice fields as reviewed and log an audit trail entry —
otherwise a high-confidence invoice skips the review queue silently with no
record it was ever "approved" (audit_log is immutable and load-bearing here).
"""
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_pipeline.db.models import AuditLog, Base, Invoice, InvoiceField
from invoice_pipeline.schemas import CanonicalizedInvoice, FieldValue, Invoice as InvoiceSchema
from invoice_pipeline.stages.ingest import ingest
from invoice_pipeline.stages.persist import persist

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _high_confidence_doc():
    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()
    doc = await ingest("auto_approve.pdf", pdf_bytes, "application/pdf")
    extracted = InvoiceSchema(
        invoice_number=FieldValue(value="INV-9001", confidence=0.95),
        total_amount=FieldValue(value="500.00", confidence=0.95),
    )
    canon = CanonicalizedInvoice(
        invoice_number="INV-9001",
        total_amount="500.00",
        raw=extracted,
        needs_review=False,
        review_reasons=[],
    )
    return doc.model_copy(update={"extracted": extracted, "canonicalized": canon})


@pytest.mark.asyncio
async def test_persist_auto_approves_high_confidence_invoice(db_session: AsyncSession):
    doc = await _high_confidence_doc()
    await persist(doc, db_session)

    inv = (await db_session.execute(select(Invoice))).scalar_one()
    assert inv.needs_review is False

    fields = (
        await db_session.execute(select(InvoiceField).where(InvoiceField.invoice_id == inv.id))
    ).scalars().all()
    assert fields, "expected at least one field row"
    assert all(f.reviewed is True for f in fields)

    audit_actions = (
        await db_session.execute(
            select(AuditLog.action).where(AuditLog.document_id == doc.document_id)
        )
    ).scalars().all()
    assert "auto_approved" in audit_actions


@pytest.mark.asyncio
async def test_persist_does_not_auto_approve_needs_review_invoice(db_session: AsyncSession):
    doc = await _high_confidence_doc()
    doc = doc.model_copy(
        update={"canonicalized": doc.canonicalized.model_copy(update={"needs_review": True})}
    )
    await persist(doc, db_session)

    inv = (await db_session.execute(select(Invoice))).scalar_one()
    assert inv.needs_review is True

    fields = (
        await db_session.execute(select(InvoiceField).where(InvoiceField.invoice_id == inv.id))
    ).scalars().all()
    assert all(f.reviewed is False for f in fields)

    audit_actions = (
        await db_session.execute(
            select(AuditLog.action).where(AuditLog.document_id == doc.document_id)
        )
    ).scalars().all()
    assert "auto_approved" not in audit_actions
