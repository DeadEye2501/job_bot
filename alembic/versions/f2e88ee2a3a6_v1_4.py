"""v1.4

Новые поля и сущности версии 1.4 — одной ревизией: ссылка на LinkedIn в анкете
и сопроводительные письма профиля.

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


def downgrade() -> None:
    op.drop_table('cover_letter')
    op.drop_column('profile', 'linkedin_url')
