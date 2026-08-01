"""phase6_jump_to_source

Revision ID: 9646dbf2266a
Revises: phase5_vendor_intelligence
Create Date: 2026-07-25 09:49:15.703428

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9646dbf2266a'
down_revision: Union[str, None] = 'phase5_vendor_intelligence'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoice_fields", sa.Column("page", sa.Integer(), nullable=True))
    op.add_column("invoice_fields", sa.Column("bbox", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("invoice_fields", "bbox")
    op.drop_column("invoice_fields", "page")
