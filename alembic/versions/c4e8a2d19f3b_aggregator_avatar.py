"""aggregator avatar

Revision ID: c4e8a2d19f3b
Revises: a9c3e1f07b42
Create Date: 2026-10-10 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e8a2d19f3b'
down_revision: Union[str, Sequence[str], None] = 'a9c3e1f07b42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('aggregator', sa.Column('avatar', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('aggregator') as batch:
        batch.drop_column('avatar')
