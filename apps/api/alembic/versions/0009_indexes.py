"""Phase 12: Missing indexes on dashboard filter/sort columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-25

"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_documents_batch_id", "documents", ["batch_id"])
    op.create_index("ix_invoices_created_at", "invoices", ["created_at"])
    op.create_index("ix_invoices_invoice_date", "invoices", ["invoice_date"])
    op.create_index("ix_line_items_invoice_id", "line_items", ["invoice_id"])
    op.create_index("ix_vendor_templates_vendor_id", "vendor_templates", ["vendor_id"])
    op.create_index("ix_reviewer_feedback_document_id", "reviewer_feedback", ["document_id"])
    op.create_index("ix_reviewer_feedback_vendor_id", "reviewer_feedback", ["vendor_id"])
    op.alter_column(
        "export_history",
        "filter_params",
        server_default=sa.text("'{}'"),
    )


def downgrade() -> None:
    op.alter_column("export_history", "filter_params", server_default=None)
    op.drop_index("ix_reviewer_feedback_vendor_id", table_name="reviewer_feedback")
    op.drop_index("ix_reviewer_feedback_document_id", table_name="reviewer_feedback")
    op.drop_index("ix_vendor_templates_vendor_id", table_name="vendor_templates")
    op.drop_index("ix_line_items_invoice_id", table_name="line_items")
    op.drop_index("ix_invoices_invoice_date", table_name="invoices")
    op.drop_index("ix_invoices_created_at", table_name="invoices")
    op.drop_index("ix_documents_batch_id", table_name="documents")
