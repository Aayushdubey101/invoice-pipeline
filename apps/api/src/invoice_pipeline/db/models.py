import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA256 hex
    filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    doc_type: Mapped[str] = mapped_column(String(32), default="unknown")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    parent_document_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("documents.id"), nullable=True
    )
    errors: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    invoice: Mapped["Invoice | None"] = relationship("Invoice", back_populates="document", uselist=False)
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="document")


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    canonical_name: Mapped[str] = mapped_column(String(512))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    embedding_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # Chroma doc ID
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="vendor")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), unique=True)
    vendor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vendors.id"), nullable=True
    )
    invoice_number: Mapped[str | None] = mapped_column(String(256), nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(String(16), nullable=True)  # YYYY-MM-DD
    due_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(256), nullable=True)
    purchase_order: Mapped[str | None] = mapped_column(String(256), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reasons: Mapped[list] = mapped_column(JSON, default=list)
    raw_extraction: Mapped[dict] = mapped_column(JSON, default=dict)  # full Invoice schema
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document: Mapped[Document] = relationship("Document", back_populates="invoice")
    vendor: Mapped[Vendor | None] = relationship("Vendor", back_populates="invoices")
    fields: Mapped[list["InvoiceField"]] = relationship("InvoiceField", back_populates="invoice")
    line_items: Mapped[list["LineItem"]] = relationship("LineItem", back_populates="invoice")


class InvoiceField(Base):
    __tablename__ = "invoice_fields"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"))
    field_name: Mapped[str] = mapped_column(String(64))
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.0)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="fields")


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit_price_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description_confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.0)
    quantity_confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.0)
    unit_price_confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.0)
    total_confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.0)

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="line_items")


class AuditLog(Base):
    """Immutable audit trail — never delete rows."""
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"))
    actor: Mapped[str] = mapped_column(String(128), default="system")
    stage: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship("Document", back_populates="audit_logs")
