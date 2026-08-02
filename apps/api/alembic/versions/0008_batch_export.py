"""Phase 11: Batch processing and export history

Revision ID: a1b2c3d4e5f6
Revises: d4c9475af6f5
Create Date: 2026-07-25

"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "d4c9475af6f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("upload_source", sa.String(64), nullable=False, server_default="web"),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.add_column(
        "documents",
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("batches.id"),
            nullable=True,
        ),
    )
    op.create_table(
        "export_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("export_type", sa.String(32), nullable=False),
        sa.Column("filter_params", sa.JSON(), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_column("documents", "batch_id")
    op.drop_table("batches")
    op.drop_table("export_history")
