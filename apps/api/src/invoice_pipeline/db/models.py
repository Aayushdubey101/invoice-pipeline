import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


# Phase 14: pre-existing rows (and any code path not yet threading a real
# workspace_id through — bridged incrementally across sub-phases 14.1-14.4)
# fall back to this one backfilled "legacy" workspace rather than failing a
# NOT NULL constraint. Matches the id the phase14 migration backfills with.
LEGACY_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


class Workspace(Base):
    """Phase 14: guest (zero-retention, expiring) or authenticated (persistent) tenant boundary."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_type: Mapped[str] = mapped_column(String(16), index=True)  # guest | authenticated | legacy
    clerk_user_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | finished
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_preference: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA256 hex, salted with workspace_id
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, default=LEGACY_WORKSPACE_ID
    )
    filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    doc_type: Mapped[str] = mapped_column(String(32), default="unknown")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    parent_document_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("documents.id"), nullable=True
    )
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("batches.id"), nullable=True, index=True
    )

    invoice: Mapped["Invoice | None"] = relationship(
        "Invoice", back_populates="document", uselist=False
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="document")
    batch: Mapped["Batch | None"] = relationship("Batch", back_populates="documents")


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    canonical_name: Mapped[str] = mapped_column(String(512))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # primary tax ID
    status: Mapped[str] = mapped_column(String(32), default="active")
    embedding_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # Chroma doc ID
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, default=LEGACY_WORKSPACE_ID
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # ── Phase 5: Vendor Intelligence Memory ─────────────────────────────────────────
    tax_ids: Mapped[list[str]] = mapped_column(
        JSON, default=list
    )  # All tax IDs seen for this vendor (append-only)
    historical_invoice_numbers: Mapped[list[str]] = mapped_column(
        JSON, default=list
    )  # All invoice numbers seen
    preferred_currency: Mapped[str | None] = mapped_column(
        String(3), nullable=True
    )  # Most frequent ISO-4217 currency
    preferred_payment_terms: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )  # Most frequent payment terms string
    frequently_used_products: Mapped[list[str]] = mapped_column(
        JSON, default=list
    )  # Top description strings from line items
    avg_confidence: Mapped[float | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )  # Rolling average extraction confidence
    invoice_count: Mapped[int] = mapped_column(
        Integer, default=0
    )  # Total invoices processed for this vendor
    layout_patterns: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict
    )  # Structural hints: {"has_line_items": bool, "typical_field_positions": ...}

    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="vendor")
    templates: Mapped[list["VendorTemplate"]] = relationship("VendorTemplate", back_populates="vendor")


class VendorTemplate(Base):
    __tablename__ = "vendor_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, default=LEGACY_WORKSPACE_ID
    )
    vendor_id: Mapped[str] = mapped_column(String(36), ForeignKey("vendors.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    
    fingerprint: Mapped[str] = mapped_column(Text)  # Regex or text snippet to identify this template
    
    # Layout learning data
    header_positions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    invoice_number_location: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    date_location: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    table_structure: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    logo_location: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    footer_pattern: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ocr_corrections: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="templates")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, default=LEGACY_WORKSPACE_ID
    )
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), unique=True)
    vendor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vendors.id"), nullable=True, index=True
    )
    invoice_number: Mapped[str | None] = mapped_column(String(256), nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(
        String(16), nullable=True, index=True
    )  # YYYY-MM-DD
    due_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(256), nullable=True)
    purchase_order: Mapped[str | None] = mapped_column(String(256), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    raw_extraction: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict
    )  # full Invoice schema
    validation_report: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, default=None
    )  # ValidationReport.model_dump()
    confidence_breakdown: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
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
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(64))
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.0)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="fields")


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # ── Raw extracted cell values ─────────────────────────────────────────────
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit_price_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ── Per-cell confidence scores ────────────────────────────────────────────
    description_confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.0)
    quantity_confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.0)
    unit_price_confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.0)
    total_confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.0)
    # ── Phase 4: Spatial metadata ─────────────────────────────────────────────
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)          # 0-indexed page
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)    # [x0,y0,x1,y1]
    source_evidence: Mapped[str | None] = mapped_column(Text, nullable=True) # surrounding text
    row_type: Mapped[str] = mapped_column(String(32), default="item")        # RowType enum value
    math_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # qty*price≈total
    table_index: Mapped[int] = mapped_column(Integer, default=0)             # which table

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="line_items")


class AuditLog(Base):
    """Immutable audit trail — never delete rows."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, default=LEGACY_WORKSPACE_ID
    )
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), index=True)
    actor: Mapped[str] = mapped_column(String(128), default="system")
    stage: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship("Document", back_populates="audit_logs")


class ReviewerFeedback(Base):
    """Phase 10: Reviewer Feedback Learning Dataset"""

    __tablename__ = "reviewer_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, default=LEGACY_WORKSPACE_ID
    )
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), index=True)
    vendor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vendors.id"), nullable=True, index=True
    )
    field_type: Mapped[str] = mapped_column(String(64))  # e.g., 'invoice_number', 'total_amount'
    invoice_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.0)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Batch(Base):
    """Phase 11: Batch upload tracking."""

    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, default=LEGACY_WORKSPACE_ID
    )
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)  # Phase 14: "Project" name
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upload_source: Mapped[str] = mapped_column(String(64), default="web")  # web, folder, email
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    pending: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    avg_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["Document"]] = relationship("Document", back_populates="batch")


class ExportHistory(Base):
    """Phase 11: Excel export history tracking."""

    __tablename__ = "export_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True, default=LEGACY_WORKSPACE_ID
    )
    export_type: Mapped[str] = mapped_column(String(32))  # single, batch, all, filtered
    filter_params: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    filename: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

