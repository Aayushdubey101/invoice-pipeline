"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("doc_type", sa.String(32), server_default="unknown"),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("parent_document_id", sa.String(64), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("errors", sa.JSON, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "vendors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_name", sa.String(512), nullable=False),
        sa.Column("aliases", sa.JSON, server_default="[]"),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("tax_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), server_default="active"),
        sa.Column("embedding_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("documents.id"), unique=True, nullable=False),
        sa.Column("vendor_id", sa.String(36), sa.ForeignKey("vendors.id"), nullable=True),
        sa.Column("invoice_number", sa.String(256), nullable=True),
        sa.Column("invoice_date", sa.String(16), nullable=True),
        sa.Column("due_date", sa.String(16), nullable=True),
        sa.Column("buyer_name", sa.String(512), nullable=True),
        sa.Column("subtotal", sa.Numeric(18, 4), nullable=True),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("total_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("payment_terms", sa.String(256), nullable=True),
        sa.Column("purchase_order", sa.String(256), nullable=True),
        sa.Column("needs_review", sa.Boolean, server_default="false"),
        sa.Column("review_reasons", sa.JSON, server_default="[]"),
        sa.Column("raw_extraction", sa.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "invoice_fields",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("field_name", sa.String(64), nullable=False),
        sa.Column("raw_value", sa.Text, nullable=True),
        sa.Column("canonical_value", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), server_default="0"),
        sa.Column("evidence", sa.Text, nullable=True),
        sa.Column("needs_review", sa.Boolean, server_default="false"),
        sa.Column("reviewed", sa.Boolean, server_default="false"),
        sa.Column("reviewed_value", sa.Text, nullable=True),
    )

    op.create_table(
        "line_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("position", sa.Integer, server_default="0"),
        sa.Column("description_raw", sa.Text, nullable=True),
        sa.Column("quantity_raw", sa.String(64), nullable=True),
        sa.Column("unit_price_raw", sa.String(64), nullable=True),
        sa.Column("total_raw", sa.String(64), nullable=True),
        sa.Column("description_confidence", sa.Numeric(4, 3), server_default="0"),
        sa.Column("quantity_confidence", sa.Numeric(4, 3), server_default="0"),
        sa.Column("unit_price_confidence", sa.Numeric(4, 3), server_default="0"),
        sa.Column("total_confidence", sa.Numeric(4, 3), server_default="0"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("actor", sa.String(128), server_default="system"),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("before_hash", sa.String(64), nullable=True),
        sa.Column("after_hash", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("metadata", sa.JSON, server_default="{}"),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_invoices_vendor_id", "invoices", ["vendor_id"])
    op.create_index("ix_invoices_needs_review", "invoices", ["needs_review"])
    op.create_index("ix_invoice_fields_invoice_id", "invoice_fields", ["invoice_id"])
    op.create_index("ix_audit_log_document_id", "audit_log", ["document_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("line_items")
    op.drop_table("invoice_fields")
    op.drop_table("invoices")
    op.drop_table("vendors")
    op.drop_table("documents")
