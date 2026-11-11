"""v1.4

Новые поля и сущности версии 1.4 — одной ревизией: ссылка на LinkedIn в анкете,
сопроводительные письма профиля и предпочтения строками вместо свободного текста.

Revision ID: f2e88ee2a3a6
Revises: 5d2e7a9c4b13
Create Date: 2026-11-11 03:40:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2e88ee2a3a6'
down_revision: Union[str, Sequence[str], None] = '5d2e7a9c4b13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Пересборка `profile` при включённых ключах упирается в ссылающиеся на неё
    # строки (`test_migration_engine.py`); гасится до первой записи.
    op.execute("PRAGMA foreign_keys=OFF")
    op.add_column('profile', sa.Column('linkedin_url', sa.String(), nullable=True))
    op.create_table('cover_letter',
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('app', sa.String(), nullable=True),
    sa.Column('app_short', sa.String(), nullable=True),
    sa.Column('en', sa.String(), nullable=True),
    sa.Column('en_short', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id')
    )
    op.create_table('profile_preference',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profile_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('ban', 'wish', 'info', name='preference_kind'), nullable=False),
    sa.Column('text', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['profile.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # Старый текст не переносится: вид каждой строки размечает человек, а не
    # миграция.
    with op.batch_alter_table('profile') as batch:
        batch.drop_column('free_preferences')


def downgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table('profile') as batch:
        batch.add_column(sa.Column('free_preferences', sa.String(), nullable=True))
    op.drop_table('profile_preference')
    op.drop_table('cover_letter')
    op.drop_column('profile', 'linkedin_url')
