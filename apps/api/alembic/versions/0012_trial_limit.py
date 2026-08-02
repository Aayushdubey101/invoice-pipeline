"""Phase 15: free-trial counter on workspaces

Revision ID: f1a2b3c4d5e6
Revises: d4e5f6a7b8c9
Create Date: 2026-08-03

"""
from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("trial_uses_remaining", sa.Integer(), nullable=False, server_default="5"),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "trial_uses_remaining")
