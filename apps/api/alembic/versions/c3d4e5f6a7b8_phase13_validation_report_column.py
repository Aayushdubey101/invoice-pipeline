"""Phase 13: Add missing validation_report/confidence_breakdown columns

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("validation_report", sa.JSON(), nullable=True))
    op.add_column("invoices", sa.Column("confidence_breakdown", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "confidence_breakdown")
    op.drop_column("invoices", "validation_report")
