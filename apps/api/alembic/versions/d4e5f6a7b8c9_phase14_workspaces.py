"""Phase 14: Workspace table + workspace_id on every top-level entity

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-29

"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

# Deterministic id for the one backfilled workspace pre-existing rows get assigned to.
_LEGACY_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

_SCOPED_TABLES = [
    "documents",
    "vendors",
    "vendor_templates",
    "invoices",
    "audit_log",
    "reviewer_feedback",
    "batches",
    "export_history",
]


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_type", sa.String(16), nullable=False),
        sa.Column("clerk_user_id", sa.String(128), nullable=True, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_preference", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workspaces_workspace_type", "workspaces", ["workspace_type"])

    op.execute(
        sa.text(
            "INSERT INTO workspaces (id, workspace_type, status) VALUES (:id, 'legacy', 'active')"
        ).bindparams(id=_LEGACY_WORKSPACE_ID)
    )

    for table in _SCOPED_TABLES:
        op.add_column(table, sa.Column("workspace_id", sa.String(36), nullable=True))

    op.add_column("batches", sa.Column("name", sa.String(256), nullable=True))
    op.add_column("batches", sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("batches", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))

    for table in _SCOPED_TABLES:
        op.execute(
            sa.text(f"UPDATE {table} SET workspace_id = :id WHERE workspace_id IS NULL").bindparams(
                id=_LEGACY_WORKSPACE_ID
            )
        )
        op.alter_column(table, "workspace_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_workspace_id", table, "workspaces", ["workspace_id"], ["id"]
        )
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])


def downgrade() -> None:
    for table in _SCOPED_TABLES:
        op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        op.drop_constraint(f"fk_{table}_workspace_id", table, type_="foreignkey")
        op.drop_column(table, "workspace_id")

    op.drop_column("batches", "archived_at")
    op.drop_column("batches", "is_archived")
    op.drop_column("batches", "name")

    op.drop_index("ix_workspaces_workspace_type", table_name="workspaces")
    op.drop_table("workspaces")
