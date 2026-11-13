"""english resume

Английское резюме профиля: путь к файлу у профиля и ссылка в анкете.

Revision ID: 8b41d6e0c7a2
Revises: 56fc744cc3df
Create Date: 2026-11-13 12:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8b41d6e0c7a2'
down_revision: Union[str, Sequence[str], None] = '56fc744cc3df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workspace', sa.Column('cv_en_path', sa.String(), server_default='', nullable=False))
    op.add_column('profile', sa.Column('resume_url_en', sa.String(), nullable=True))


def downgrade() -> None:
    # Пересборка `profile` и `workspace` при включённых ключах упирается в
    # ссылающиеся на них строки (`test_migration_engine.py`).
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table('profile') as batch:
        batch.drop_column('resume_url_en')
    with op.batch_alter_table('workspace') as batch:
        batch.drop_column('cv_en_path')
