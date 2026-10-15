"""vacancy language

Revision ID: a7c2e9d41b06
Revises: f3b8d1c2a7e4
Create Date: 2026-10-15 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c2e9d41b06'
down_revision: Union[str, Sequence[str], None] = 'f3b8d1c2a7e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('vacancy', sa.Column('language', sa.String(), nullable=True))


def downgrade() -> None:
    # Колонку SQLite снимает пересборкой таблицы, а пересборка таблицы, на
    # которую ссылаются, при включённых ключах падает.
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table('vacancy', recreate='always') as batch:
        batch.drop_column('language')
