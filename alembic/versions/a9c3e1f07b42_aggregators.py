"""aggregators

Revision ID: a9c3e1f07b42
Revises: e560edf8b958
Create Date: 2026-10-09 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9c3e1f07b42'
down_revision: Union[str, Sequence[str], None] = 'e560edf8b958'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOURCE_COLUMNS = ('source_aggregator_id', 'source_key')
_PROFILE_COLUMNS = (
    'expected_salary', 'expected_salary_currency', 'expected_salary_period',
    'first_name_latin', 'last_name_latin', 'gender',
)


def _source_columns(table: str) -> None:
    op.add_column(
        table,
        sa.Column('source_aggregator_id', sa.Integer(),
                  sa.ForeignKey('aggregator.id'), nullable=True),
        inline_references=True,
    )
    op.add_column(table, sa.Column('source_key', sa.String(), nullable=True))


def upgrade() -> None:
    aggregator = op.create_table(
        'aggregator',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('host', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('is_logged_in', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('avatar', sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_aggregator_host', 'aggregator', ['host'], unique=True)
    # Строка нужна каждому; входа у поиска по сети нет, поэтому сразу «вошёл».
    op.bulk_insert(aggregator, [
        {'name': 'Поиск по сети', 'host': None, 'is_active': False, 'is_logged_in': True},
    ])

    op.create_table(
        'vacancy_contact',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vacancy_id', sa.Integer(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('match_key', sa.String(), nullable=False),
        sa.Column('added_by', sa.Enum('parse', 'agent', 'user', name='contact_added_by'), nullable=False),
        sa.ForeignKeyConstraint(['vacancy_id'], ['vacancy.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_vacancy_contact_key', 'vacancy_contact', ['vacancy_id', 'match_key'], unique=True)
    op.create_index('ix_vacancy_contact_match_key', 'vacancy_contact', ['match_key'], unique=False)

    op.create_table(
        'application',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vacancy_id', sa.Integer(), nullable=False),
        sa.Column('aggregator_id', sa.Integer(), nullable=True),
        sa.Column('via', sa.Enum('aggregator', 'form', 'email', name='application_via'), nullable=False),
        sa.Column('target', sa.String(), nullable=False),
        sa.Column('letter', sa.String(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('chat_anchor', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['vacancy_id'], ['vacancy.id']),
        sa.ForeignKeyConstraint(['aggregator_id'], ['aggregator.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_application_vacancy_id', 'application', ['vacancy_id'], unique=False)

    op.create_table(
        'screening',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('from_us', sa.Boolean(), nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['application.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_screening_position', 'screening', ['application_id', 'position'], unique=True)

    op.create_table(
        'mail_account',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('address', sa.String(), nullable=True),
        sa.Column('smtp_host', sa.String(), nullable=True),
        sa.Column('smtp_port', sa.Integer(), nullable=True),
        sa.Column('password_encrypted', sa.String(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('id = 1', name='ck_mail_account_singleton'),
        sa.PrimaryKeyConstraint('id'),
    )

    _source_columns('vacancy')
    op.create_index('uq_vacancy_aggregator_key', 'vacancy', ['source_aggregator_id', 'source_key'], unique=True)
    _source_columns('trash_event')
    op.create_index('ix_trash_event_aggregator_key', 'trash_event', ['source_aggregator_id', 'source_key'], unique=False)

    op.add_column('profile', sa.Column('expected_salary', sa.Integer(), nullable=True))
    op.add_column('profile', sa.Column('expected_salary_currency', sa.String(), nullable=True))
    op.add_column('profile', sa.Column('expected_salary_period', sa.Enum('hour', 'month', 'year', name='salary_period'), nullable=True))
    op.add_column('profile', sa.Column('first_name_latin', sa.String(), nullable=True))
    op.add_column('profile', sa.Column('last_name_latin', sa.String(), nullable=True))
    op.add_column('profile', sa.Column('gender', sa.Enum('male', 'female', name='gender'), nullable=True))


def downgrade() -> None:
    # Колонку под внешним ключом SQLite снимает только пересборкой таблицы, а
    # пересборка при включённых ключах падает.
    op.execute("PRAGMA foreign_keys=OFF")
    op.drop_index('ix_trash_event_aggregator_key', table_name='trash_event')
    op.drop_index('uq_vacancy_aggregator_key', table_name='vacancy')
    for table, columns in (
        ('trash_event', _SOURCE_COLUMNS),
        ('vacancy', _SOURCE_COLUMNS),
        ('profile', _PROFILE_COLUMNS),
    ):
        with op.batch_alter_table(table, recreate='always') as batch:
            for column in columns:
                batch.drop_column(column)
    op.drop_table('mail_account')
    op.drop_index('uq_screening_position', table_name='screening')
    op.drop_table('screening')
    op.drop_index('ix_application_vacancy_id', table_name='application')
    op.drop_table('application')
    op.drop_index('ix_vacancy_contact_match_key', table_name='vacancy_contact')
    op.drop_index('uq_vacancy_contact_key', table_name='vacancy_contact')
    op.drop_table('vacancy_contact')
    op.drop_index('uq_aggregator_host', table_name='aggregator')
    op.drop_table('aggregator')
