import pytest
from sqlalchemy import select
from invoice_pipeline.schemas import Document, DocumentStatus, Invoice, FieldValue, CanonicalizedInvoice
from invoice_pipeline.db.models import Vendor, VendorTemplate
from invoice_pipeline.pipeline import run_pipeline
from invoice_pipeline.templates.detect import apply_vendor_templates
from invoice_pipeline.templates.learner import learn_vendor_template
from datetime import date
from decimal import Decimal
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from invoice_pipeline.db.models import Base

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
async def test_vendor_template_learning(db_session):
    # Create a vendor
    v = Vendor(id="vendor-123", canonical_name="Test Vendor Inc", status="active")
    db_session.add(v)
    await db_session.commit()

    # Create a dummy document with canonicalized invoice matching the vendor
    raw_invoice = Invoice(
        vendor_name=FieldValue(value="Test Vendor Inc"),
        invoice_number=FieldValue(value="INV-001", bbox=(10.0, 20.0, 100.0, 40.0)),
        invoice_date=FieldValue(value="2023-01-01", bbox=(50.0, 60.0, 120.0, 80.0)),
    )
    
    canon = CanonicalizedInvoice(
        vendor_id="vendor-123",
        invoice_number="INV-001",
        invoice_date=date(2023, 1, 1),
        raw=raw_invoice,
        needs_review=False
    )
    
    doc = Document(
        document_id="doc-888",
        filename="test.pdf",
        mime_type="application/pdf",
        raw_text="Test Vendor Inc Invoice INV-001",
        canonicalized=canon
    )

    # Learn template
    await learn_vendor_template(doc, db_session)

    # Verify template was created
    stmt = select(VendorTemplate).where(VendorTemplate.vendor_id == "vendor-123")
    result = await db_session.execute(stmt)
    tmpl = result.scalars().first()
    
    assert tmpl is not None
    assert tmpl.fingerprint == "Test Vendor Inc"
    assert tmpl.invoice_number_location == [10.0, 20.0, 100.0, 40.0]
    assert tmpl.date_location == [50.0, 60.0, 120.0, 80.0]

@pytest.mark.asyncio
async def test_apply_vendor_template(db_session):
    # Add a template to the database
    v = Vendor(id="vendor-999", canonical_name="Acme Corp", status="active")
    tmpl = VendorTemplate(
        vendor_id="vendor-999",
        version=1,
        fingerprint="Acme Corp",
        invoice_number_location={"x0": 10, "y0": 20, "x1": 50, "y1": 30}
    )
    db_session.add(v)
    db_session.add(tmpl)
    await db_session.commit()

    # Test applying it to a document with matching text
    doc = Document(
        document_id="doc-999",
        filename="acme.pdf",
        mime_type="application/pdf",
        raw_text="This is an Acme Corp invoice.\nPlease pay."
    )
    
    new_doc = await apply_vendor_templates(doc, db_session)
    
    assert "VENDOR TEMPLATE DETECTED: Acme Corp" in new_doc.raw_text
    assert "Hint: Invoice Number is typically located around bbox" in new_doc.raw_text

