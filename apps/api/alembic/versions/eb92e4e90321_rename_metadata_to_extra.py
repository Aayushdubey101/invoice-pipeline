"""rename_metadata_to_extra

Revision ID: eb92e4e90321
Revises: 0001
Create Date: 2026-05-24 11:00:02.607035

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'eb92e4e90321'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('audit_log', 'metadata', new_column_name='extra')


def downgrade() -> None:
    op.alter_column('audit_log', 'extra', new_column_name='metadata')

