"""resume autofill

Revision ID: f3b8d1c2a7e4
Revises: 6cc10045aeb6
Create Date: 2026-10-14 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3b8d1c2a7e4'
down_revision: Union[str, Sequence[str], None] = '6cc10045aeb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROFILE_COLUMNS = (
    'patronymic', 'patronymic_latin', 'birth_date', 'citizenship', 'about_me', 'resume_url',
)


def upgrade() -> None:
    op.add_column('profile', sa.Column('patronymic', sa.String(), nullable=True))
    op.add_column('profile', sa.Column('patronymic_latin', sa.String(), nullable=True))
    op.add_column('profile', sa.Column('birth_date', sa.Date(), nullable=True))
    op.add_column('profile', sa.Column('citizenship', sa.String(), nullable=True))
    op.add_column('profile', sa.Column('about_me', sa.String(), nullable=True))
    op.add_column('profile', sa.Column('resume_url', sa.String(), nullable=True))
    op.add_column('aggregator', sa.Column('can_add_resume', sa.Boolean(), server_default=sa.text('0'), nullable=False))

    op.create_table(
        'aggregator_resume',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('aggregator_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('is_chosen', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.ForeignKeyConstraint(['aggregator_id'], ['aggregator.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_aggregator_resume_url', 'aggregator_resume', ['aggregator_id', 'url'], unique=True)
    op.create_index('uq_aggregator_resume_chosen', 'aggregator_resume', ['aggregator_id'], unique=True, postgresql_where=sa.text('is_chosen'), sqlite_where=sa.text('is_chosen'))


def downgrade() -> None:
    op.drop_index('uq_aggregator_resume_chosen', table_name='aggregator_resume', postgresql_where=sa.text('is_chosen'), sqlite_where=sa.text('is_chosen'))
    op.drop_index('uq_aggregator_resume_url', table_name='aggregator_resume')
    op.drop_table('aggregator_resume')
    # Колонку SQLite снимает пересборкой таблицы, а пересборка таблицы, на
    # которую ссылаются, при включённых ключах падает.
    op.execute("PRAGMA foreign_keys=OFF")
    for table, columns in (
        ('aggregator', ('can_add_resume',)),
        ('profile', _PROFILE_COLUMNS),
    ):
        with op.batch_alter_table(table, recreate='always') as batch:
            for column in columns:
                batch.drop_column(column)
