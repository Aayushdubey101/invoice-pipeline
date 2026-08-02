"""Phase 5: Vendor Intelligence — Alembic migration

Revision ID: phase5_vendor_intelligence
Revises: phase4_line_items
Create Date: 2026-07-25

Adds vendor memory columns to the vendors table:
  - tax_ids (JSON, all historical tax IDs, append-only)
  - historical_invoice_numbers (JSON)
  - preferred_currency (VARCHAR 3)
  - preferred_payment_terms (VARCHAR 256)
  - frequently_used_products (JSON)
  - avg_confidence (NUMERIC 4,3)
  - invoice_count (INTEGER default 0)
  - layout_patterns (JSON)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "phase5_vendor_intelligence"
down_revision = "phase4_line_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vendors", sa.Column("tax_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column(
        "vendors",
        sa.Column(
            "historical_invoice_numbers", sa.JSON(), nullable=False, server_default="[]"
        ),
    )
    op.add_column(
        "vendors", sa.Column("preferred_currency", sa.String(length=3), nullable=True)
    )
    op.add_column(
        "vendors",
        sa.Column("preferred_payment_terms", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("frequently_used_products", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "vendors", sa.Column("avg_confidence", sa.Numeric(4, 3), nullable=True)
    )
    op.add_column(
        "vendors",
        sa.Column("invoice_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "vendors",
        sa.Column("layout_patterns", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("vendors", "layout_patterns")
    op.drop_column("vendors", "invoice_count")
    op.drop_column("vendors", "avg_confidence")
    op.drop_column("vendors", "frequently_used_products")
    op.drop_column("vendors", "preferred_payment_terms")
    op.drop_column("vendors", "preferred_currency")
    op.drop_column("vendors", "historical_invoice_numbers")
    op.drop_column("vendors", "tax_ids")
