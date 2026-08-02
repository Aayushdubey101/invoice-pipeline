"""Phase 4: Advanced Line Item Extraction — add rich columns to line_items

Revision ID: phase4_line_items
Revises: eb92e4e90321
Create Date: 2026-07-25

Adds columns to line_items:
  - page (INTEGER, nullable)
  - bbox (JSON, nullable)
  - source_evidence (TEXT, nullable)
  - row_type (VARCHAR(32), default 'item')
  - math_valid (BOOLEAN, nullable)
  - table_index (INTEGER, default 0)
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "phase4_line_items"
down_revision = "eb92e4e90321"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("line_items", sa.Column("page", sa.Integer(), nullable=True))
    op.add_column("line_items", sa.Column("bbox", sa.JSON(), nullable=True))
    op.add_column("line_items", sa.Column("source_evidence", sa.Text(), nullable=True))
    op.add_column(
        "line_items",
        sa.Column("row_type", sa.String(length=32), nullable=False, server_default="item"),
    )
    op.add_column("line_items", sa.Column("math_valid", sa.Boolean(), nullable=True))
    op.add_column(
        "line_items",
        sa.Column("table_index", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("line_items", "table_index")
    op.drop_column("line_items", "math_valid")
    op.drop_column("line_items", "row_type")
    op.drop_column("line_items", "source_evidence")
    op.drop_column("line_items", "bbox")
    op.drop_column("line_items", "page")
