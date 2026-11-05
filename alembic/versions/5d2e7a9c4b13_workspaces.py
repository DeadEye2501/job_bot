"""workspaces

Профили: таблица `workspace`, тумблеры, отметки чтения и выбор резюме в
строках «профиль × предмет», `workspace_id` у вакансии, отметки мусора и
анкеты. Всё, что уже есть в базе, уходит в первый профиль, и он активен.

Revision ID: 5d2e7a9c4b13
Revises: 032b8b1c9f8a
Create Date: 2026-11-05 20:00:00.000000+00:00

"""
from typing import Callable, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5d2e7a9c4b13'
down_revision: Union[str, Sequence[str], None] = '032b8b1c9f8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE = '(SELECT id FROM workspace WHERE is_active)'


def upgrade() -> None:
    # Пересборка таблиц при включённых ключах снесла бы каскадом строки,
    # ссылающиеся на них (`test_migration_engine.py`).
    op.execute("PRAGMA foreign_keys=OFF")
    _create_workspace()
    _create_switch_tables()
    _move_switches()
    _drop_shared_switches()
    _add_workspace_id('vacancy', _vacancy_source_per_workspace)
    _add_workspace_id('trash_event')
    _add_workspace_id('profile', _one_profile_per_workspace)


def _create_workspace() -> None:
    op.create_table('workspace',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('cv_path', sa.String(), server_default='', nullable=False),
    sa.Column('photo_path', sa.String(), server_default='', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_workspace_active', 'workspace', ['is_active'], unique=True, postgresql_where=sa.text('is_active'), sqlite_where=sa.text('is_active'))
    op.execute(
        "INSERT INTO workspace (id, is_active, cv_path, photo_path) VALUES (1, 1, "
        "coalesce((SELECT value FROM app_settings WHERE key = 'cv_path'), ''), "
        "coalesce((SELECT value FROM app_settings WHERE key = 'photo_path'), ''))"
    )
    op.execute("DELETE FROM app_settings WHERE key IN ('cv_path', 'photo_path')")


def _create_switch_tables() -> None:
    op.create_table('workspace_channel',
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('channel_id', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_processed_msg_id', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['channel_id'], ['telegram_channel.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id', 'channel_id')
    )
    op.create_table('workspace_aggregator',
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('aggregator_id', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('chosen_resume_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['aggregator_id'], ['aggregator.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['chosen_resume_id'], ['aggregator_resume.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id', 'aggregator_id')
    )
    op.create_table('workspace_blacklist',
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('blacklist_id', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.ForeignKeyConstraint(['blacklist_id'], ['blacklist.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id', 'blacklist_id')
    )


def _move_switches() -> None:
    """В первый профиль — только строки, отличные от «строки нет»: её
    отсутствие и значит «выключено, не читано, не выбрано»."""
    op.execute(
        "INSERT INTO workspace_channel (workspace_id, channel_id, is_active, last_processed_msg_id) "
        "SELECT 1, id, is_active, last_processed_msg_id FROM telegram_channel "
        "WHERE is_active OR last_processed_msg_id IS NOT NULL"
    )
    chosen = (
        "(SELECT r.id FROM aggregator_resume r "
        "WHERE r.aggregator_id = aggregator.id AND r.is_chosen)"
    )
    op.execute(
        "INSERT INTO workspace_aggregator "
        "(workspace_id, aggregator_id, is_active, last_run_at, chosen_resume_id) "
        f"SELECT 1, id, is_active, last_run_at, {chosen} FROM aggregator "
        f"WHERE is_active OR last_run_at IS NOT NULL OR {chosen} IS NOT NULL"
    )
    op.execute(
        "INSERT INTO workspace_blacklist (workspace_id, blacklist_id, active) "
        "SELECT 1, id, active FROM blacklist WHERE active"
    )


def _drop_shared_switches() -> None:
    with op.batch_alter_table('aggregator_resume') as batch:
        batch.drop_index('uq_aggregator_resume_chosen', sqlite_where=sa.text('is_chosen'))
        batch.drop_column('is_chosen')
    with op.batch_alter_table('telegram_channel') as batch:
        batch.drop_column('is_active')
        batch.drop_column('last_processed_msg_id')
    with op.batch_alter_table('aggregator') as batch:
        batch.drop_column('is_active')
        batch.drop_column('last_run_at')
    with op.batch_alter_table('blacklist') as batch:
        batch.drop_column('active')


def _add_workspace_id(table: str, *uniques: Callable) -> None:
    """Колонка сначала обнуляемая: у живых строк значения ещё нет.

    Сырым SQL, потому что batch-режим принимает внешний ключ только с именем,
    а у всех ключей схемы имён нет. Пересборка ниже подхватывает его отражением
    и заодно ставит уникальности таблицы с профилем (`uniques`): так таблица
    пересобирается один раз.
    """
    op.execute(f"ALTER TABLE {table} ADD COLUMN workspace_id INTEGER REFERENCES workspace (id)")
    op.execute(f"UPDATE {table} SET workspace_id = 1")
    with op.batch_alter_table(table, recreate='always') as batch:
        batch.alter_column('workspace_id', existing_type=sa.Integer(), nullable=False)
        for unique in uniques:
            unique(batch)


def _vacancy_source_per_workspace(batch) -> None:
    """Источник вакансии уникален внутри профиля."""
    batch.drop_constraint('uq_vacancy_source', type_='unique')
    batch.create_unique_constraint('uq_vacancy_source', ['source_channel_id', 'source_msg_id', 'workspace_id'])
    batch.drop_index('uq_vacancy_aggregator_key')
    batch.create_index('uq_vacancy_aggregator_key', ['source_aggregator_id', 'source_key', 'workspace_id'], unique=True)


def _one_profile_per_workspace(batch) -> None:
    batch.create_unique_constraint('uq_profile_workspace', ['workspace_id'])


def downgrade() -> None:
    """Значения активного профиля возвращаются в общие колонки; данные
    остальных профилей удаляются — прежней схеме их негде держать."""
    op.execute("PRAGMA foreign_keys=OFF")
    _restore_shared_switches()
    _drop_other_workspaces()
    _drop_workspace_id()
    op.drop_table('workspace_blacklist')
    op.drop_table('workspace_aggregator')
    op.drop_table('workspace_channel')
    op.drop_index('uq_workspace_active', table_name='workspace', sqlite_where=sa.text('is_active'))
    op.drop_table('workspace')


def _restore_shared_switches() -> None:
    with op.batch_alter_table('telegram_channel') as batch:
        batch.add_column(sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False))
        batch.add_column(sa.Column('last_processed_msg_id', sa.BigInteger(), nullable=True))
    with op.batch_alter_table('aggregator') as batch:
        batch.add_column(sa.Column('is_active', sa.Boolean(), server_default=sa.text('0'), nullable=False))
        batch.add_column(sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table('aggregator_resume') as batch:
        batch.add_column(sa.Column('is_chosen', sa.Boolean(), server_default=sa.text('0'), nullable=False))
    with op.batch_alter_table('blacklist') as batch:
        batch.add_column(sa.Column('active', sa.Boolean(), server_default=sa.text('1'), nullable=False))

    channel = f"FROM workspace_channel s WHERE s.channel_id = telegram_channel.id AND s.workspace_id = {_ACTIVE}"
    op.execute(
        f"UPDATE telegram_channel SET is_active = coalesce((SELECT s.is_active {channel}), 0), "
        f"last_processed_msg_id = (SELECT s.last_processed_msg_id {channel})"
    )
    site = f"FROM workspace_aggregator s WHERE s.aggregator_id = aggregator.id AND s.workspace_id = {_ACTIVE}"
    op.execute(
        f"UPDATE aggregator SET is_active = coalesce((SELECT s.is_active {site}), 0), "
        f"last_run_at = (SELECT s.last_run_at {site})"
    )
    op.execute(
        "UPDATE aggregator_resume SET is_chosen = EXISTS (SELECT 1 FROM workspace_aggregator s "
        f"WHERE s.chosen_resume_id = aggregator_resume.id AND s.workspace_id = {_ACTIVE})"
    )
    op.execute(
        "UPDATE blacklist SET active = coalesce((SELECT s.active FROM workspace_blacklist s "
        f"WHERE s.blacklist_id = blacklist.id AND s.workspace_id = {_ACTIVE}), 0)"
    )
    op.create_index('uq_aggregator_resume_chosen', 'aggregator_resume', ['aggregator_id'], unique=True, postgresql_where=sa.text('is_chosen'), sqlite_where=sa.text('is_chosen'))
    op.execute(
        "INSERT INTO app_settings (key, value) "
        "SELECT 'cv_path', cv_path FROM workspace WHERE is_active "
        "UNION ALL SELECT 'photo_path', photo_path FROM workspace WHERE is_active"
    )


def _drop_other_workspaces() -> None:
    """Удаление в порядке ссылок: ключи погашены, и порядок держит код."""
    vacancies = f"(SELECT id FROM vacancy WHERE workspace_id != {_ACTIVE})"
    profiles = f"(SELECT id FROM profile WHERE workspace_id != {_ACTIVE})"
    experience = f"(SELECT id FROM profile_experience WHERE profile_id IN {profiles})"
    projects = f"(SELECT id FROM profile_project WHERE profile_id IN {profiles})"
    for sql in (
        f"UPDATE message SET vacancy_id = NULL WHERE vacancy_id IN {vacancies}",
        "DELETE FROM screening WHERE application_id IN "
        f"(SELECT id FROM application WHERE vacancy_id IN {vacancies})",
        f"DELETE FROM application WHERE vacancy_id IN {vacancies}",
        f"DELETE FROM vacancy_contact WHERE vacancy_id IN {vacancies}",
        f"DELETE FROM vacancy_status_history WHERE vacancy_id IN {vacancies}",
        f"DELETE FROM vacancy_event WHERE vacancy_id IN {vacancies}",
        f"DELETE FROM vacancy WHERE workspace_id != {_ACTIVE}",
        f"DELETE FROM trash_event WHERE workspace_id != {_ACTIVE}",
        f"DELETE FROM profile_experience_skills WHERE experience_id IN {experience}",
        f"DELETE FROM profile_project_skills WHERE project_id IN {projects}",
        f"DELETE FROM profile_experience WHERE profile_id IN {profiles}",
        f"DELETE FROM profile_project WHERE profile_id IN {profiles}",
        f"DELETE FROM profile_skills WHERE profile_id IN {profiles}",
        f"DELETE FROM profile_language WHERE profile_id IN {profiles}",
        f"DELETE FROM profile WHERE workspace_id != {_ACTIVE}",
    ):
        op.execute(sql)


def _drop_workspace_id() -> None:
    with op.batch_alter_table('vacancy', recreate='always') as batch:
        batch.drop_constraint('uq_vacancy_source', type_='unique')
        batch.drop_index('uq_vacancy_aggregator_key')
        batch.drop_column('workspace_id')
        batch.create_unique_constraint('uq_vacancy_source', ['source_channel_id', 'source_msg_id'])
        batch.create_index('uq_vacancy_aggregator_key', ['source_aggregator_id', 'source_key'], unique=True)
    with op.batch_alter_table('profile', recreate='always') as batch:
        batch.drop_constraint('uq_profile_workspace', type_='unique')
        batch.drop_column('workspace_id')
    with op.batch_alter_table('trash_event', recreate='always') as batch:
        batch.drop_column('workspace_id')
