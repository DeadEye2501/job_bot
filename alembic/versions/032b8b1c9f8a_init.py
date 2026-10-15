"""init

Вся схема одной ревизией: прежняя цепочка миграций сведена в неё, а база,
поднятая той цепочкой, отмечена этой ревизией без перестройки.

Revision ID: 032b8b1c9f8a
Revises:
Create Date: 2026-10-15 02:33:22.174051+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '032b8b1c9f8a'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    aggregator = op.create_table('aggregator',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('host', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('is_logged_in', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('avatar', sa.LargeBinary(), nullable=True),
    sa.Column('can_add_resume', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_aggregator_host', 'aggregator', ['host'], unique=True)
    # Строка нужна каждому; входа у поиска по сети нет, поэтому сразу «вошёл».
    op.bulk_insert(aggregator, [
        {'name': 'Поиск по сети', 'host': None, 'is_active': False, 'is_logged_in': True},
    ])
    op.create_table('app_settings',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', sa.String(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('blacklist',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('value', sa.String(), nullable=False),
    sa.Column('reason', sa.String(), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bot_state',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.Enum('Off', 'DM Only', 'Full', name='bot_mode'), server_default=sa.text("'Off'"), nullable=False),
    sa.CheckConstraint('id = 1', name='ck_bot_state_singleton'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('company',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('aliases', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('website', sa.String(), nullable=True),
    sa.Column('notes', sa.String(), nullable=True),
    sa.Column('avatar', sa.LargeBinary(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('hr',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('telegram_username', sa.String(), nullable=True),
    sa.Column('telegram_user_id', sa.BigInteger(), nullable=True),
    sa.Column('notes', sa.String(), nullable=True),
    sa.Column('avatar', sa.LargeBinary(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_hr_telegram_user_id', 'hr', ['telegram_user_id'], unique=True, postgresql_where=sa.text('telegram_user_id IS NOT NULL'), sqlite_where=sa.text('telegram_user_id IS NOT NULL'))
    op.create_table('llm_config',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('chat', 'embed', name='llm_config_kind'), nullable=False),
    sa.Column('base_url', sa.String(), nullable=True),
    sa.Column('api_key_encrypted', sa.String(), nullable=True),
    sa.Column('model', sa.String(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('kind', name='uq_llm_config_kind')
    )
    op.create_table('mail_account',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('address', sa.String(), nullable=True),
    sa.Column('smtp_host', sa.String(), nullable=True),
    sa.Column('smtp_port', sa.Integer(), nullable=True),
    sa.Column('password_encrypted', sa.String(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('id = 1', name='ck_mail_account_singleton'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('profile',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('first_name', sa.String(), nullable=False),
    sa.Column('last_name', sa.String(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('phone', sa.String(), nullable=True),
    sa.Column('location', sa.String(), nullable=True),
    sa.Column('telegram_username', sa.String(), nullable=True),
    sa.Column('github_url', sa.String(), nullable=True),
    sa.Column('education', sa.String(), nullable=True),
    sa.Column('work_format', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('grades', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('free_preferences', sa.String(), nullable=True),
    sa.Column('expected_salary', sa.Integer(), nullable=True),
    sa.Column('expected_salary_currency', sa.String(), nullable=True),
    sa.Column('expected_salary_period', sa.Enum('hour', 'month', 'year', name='salary_period'), nullable=True),
    sa.Column('first_name_latin', sa.String(), nullable=True),
    sa.Column('last_name_latin', sa.String(), nullable=True),
    sa.Column('gender', sa.Enum('male', 'female', name='gender'), nullable=True),
    sa.Column('patronymic', sa.String(), nullable=True),
    sa.Column('patronymic_latin', sa.String(), nullable=True),
    sa.Column('birth_date', sa.Date(), nullable=True),
    sa.Column('citizenship', sa.String(), nullable=True),
    sa.Column('about_me', sa.String(), nullable=True),
    sa.Column('resume_url', sa.String(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('telegram_channel',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(), nullable=True),
    sa.Column('title', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
    sa.Column('last_processed_msg_id', sa.BigInteger(), nullable=True),
    sa.Column('avatar', sa.LargeBinary(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tg_account',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('api_id', sa.Integer(), nullable=True),
    sa.Column('api_hash_encrypted', sa.String(), nullable=True),
    sa.Column('phone', sa.String(), nullable=True),
    sa.Column('password_encrypted', sa.String(), nullable=True),
    sa.Column('session_blob_encrypted', sa.LargeBinary(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('id = 1', name='ck_tg_account_singleton'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('aggregator_resume',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('aggregator_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('url', sa.String(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('is_chosen', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.ForeignKeyConstraint(['aggregator_id'], ['aggregator.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_aggregator_resume_chosen', 'aggregator_resume', ['aggregator_id'], unique=True, postgresql_where=sa.text('is_chosen'), sqlite_where=sa.text('is_chosen'))
    op.create_index('uq_aggregator_resume_url', 'aggregator_resume', ['aggregator_id', 'url'], unique=True)
    op.create_table('profile_experience',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profile_id', sa.Integer(), nullable=False),
    sa.Column('company', sa.String(), nullable=False),
    sa.Column('company_url', sa.String(), nullable=True),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('achievements', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('responsibilities', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['profile.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('profile_language',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profile_id', sa.Integer(), nullable=False),
    sa.Column('language', sa.String(), nullable=False),
    sa.Column('level', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['profile.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('profile_id', 'language')
    )
    op.create_table('profile_project',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profile_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('url', sa.String(), nullable=True),
    sa.Column('about', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['profile.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('profile_skills',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profile_id', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('aliases', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['profile.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('trash_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_channel_id', sa.Integer(), nullable=True),
    sa.Column('source_msg_id', sa.BigInteger(), nullable=True),
    sa.Column('source_aggregator_id', sa.Integer(), nullable=True),
    sa.Column('source_key', sa.String(), nullable=True),
    sa.Column('reason', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['source_aggregator_id'], ['aggregator.id'], ),
    sa.ForeignKeyConstraint(['source_channel_id'], ['telegram_channel.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_trash_event_aggregator_key', 'trash_event', ['source_aggregator_id', 'source_key'], unique=False)
    op.create_index('ix_trash_event_channel_created', 'trash_event', ['source_channel_id', 'created_at'], unique=False)
    op.create_table('vacancy',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('hr_id', sa.Integer(), nullable=True),
    sa.Column('company_id', sa.Integer(), nullable=True),
    sa.Column('source_channel_id', sa.Integer(), nullable=True),
    sa.Column('source_msg_id', sa.BigInteger(), nullable=True),
    sa.Column('source_aggregator_id', sa.Integer(), nullable=True),
    sa.Column('source_key', sa.String(), nullable=True),
    sa.Column('raw_text', sa.String(), nullable=True),
    sa.Column('embedding', sa.JSON(), nullable=True),
    sa.Column('title', sa.String(), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('company_name', sa.String(), nullable=True),
    sa.Column('hr_contact', sa.String(), nullable=True),
    sa.Column('stack', sa.JSON(), nullable=True),
    sa.Column('grade', sa.String(), nullable=True),
    sa.Column('salary', sa.String(), nullable=True),
    sa.Column('salary_min', sa.Integer(), nullable=True),
    sa.Column('salary_max', sa.Integer(), nullable=True),
    sa.Column('salary_currency', sa.String(), nullable=True),
    sa.Column('remote', sa.String(), nullable=True),
    sa.Column('location', sa.String(), nullable=True),
    sa.Column('language', sa.String(), nullable=True),
    sa.Column('score', sa.Integer(), nullable=True),
    sa.Column('skip_reason', sa.String(), nullable=True),
    sa.Column('source_url', sa.String(), nullable=True),
    sa.Column('status', sa.Enum('New', 'Applied', 'Answered', 'Test', 'Invitation', 'In Progress', 'Decline', 'Ghosting', 'Scam', 'Not Fit', 'Offer', name='vacancy_status'), server_default=sa.text("'New'"), nullable=False),
    sa.Column('is_parsed', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('notes', sa.String(), nullable=True),
    sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['company.id'], ),
    sa.ForeignKeyConstraint(['hr_id'], ['hr.id'], ),
    sa.ForeignKeyConstraint(['source_aggregator_id'], ['aggregator.id'], ),
    sa.ForeignKeyConstraint(['source_channel_id'], ['telegram_channel.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_channel_id', 'source_msg_id', name='uq_vacancy_source')
    )
    op.create_index('ix_vacancy_company_id_is_parsed', 'vacancy', ['company_id', 'is_parsed'], unique=False)
    op.create_index('ix_vacancy_hr_id_is_parsed', 'vacancy', ['hr_id', 'is_parsed'], unique=False)
    op.create_index('uq_vacancy_aggregator_key', 'vacancy', ['source_aggregator_id', 'source_key'], unique=True)
    op.create_table('application',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('vacancy_id', sa.Integer(), nullable=False),
    sa.Column('aggregator_id', sa.Integer(), nullable=True),
    sa.Column('via', sa.Enum('telegram', 'aggregator', 'form', 'email', name='application_via'), nullable=False),
    sa.Column('target', sa.String(), nullable=False),
    sa.Column('letter', sa.String(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('chat_anchor', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['aggregator_id'], ['aggregator.id'], ),
    sa.ForeignKeyConstraint(['vacancy_id'], ['vacancy.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_application_vacancy_id', 'application', ['vacancy_id'], unique=False)
    op.create_table('message',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('is_incoming', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('hr_id', sa.Integer(), nullable=True),
    sa.Column('vacancy_id', sa.Integer(), nullable=True),
    sa.Column('text', sa.String(), nullable=False),
    sa.Column('tg_message_id', sa.BigInteger(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_edited', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('media_kind', sa.String(), nullable=True),
    sa.Column('media_path', sa.String(), nullable=True),
    sa.Column('media_name', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['hr_id'], ['hr.id'], ),
    sa.ForeignKeyConstraint(['vacancy_id'], ['vacancy.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('hr_id', 'tg_message_id', 'is_incoming', name='uq_message_hr_tgid_dir')
    )
    op.create_index('ix_message_vacancy_id', 'message', ['vacancy_id'], unique=False)
    op.create_table('profile_experience_skills',
    sa.Column('experience_id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['experience_id'], ['profile_experience.id'], ),
    sa.ForeignKeyConstraint(['skill_id'], ['profile_skills.id'], ),
    sa.PrimaryKeyConstraint('experience_id', 'skill_id')
    )
    op.create_table('profile_project_skills',
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['profile_project.id'], ),
    sa.ForeignKeyConstraint(['skill_id'], ['profile_skills.id'], ),
    sa.PrimaryKeyConstraint('project_id', 'skill_id')
    )
    op.create_table('vacancy_contact',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('vacancy_id', sa.Integer(), nullable=False),
    sa.Column('value', sa.String(), nullable=False),
    sa.Column('match_key', sa.String(), nullable=False),
    sa.Column('added_by', sa.Enum('parse', 'agent', 'user', name='contact_added_by'), nullable=False),
    sa.ForeignKeyConstraint(['vacancy_id'], ['vacancy.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_vacancy_contact_match_key', 'vacancy_contact', ['match_key'], unique=False)
    op.create_index('uq_vacancy_contact_key', 'vacancy_contact', ['vacancy_id', 'match_key'], unique=True)
    op.create_table('vacancy_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('vacancy_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['vacancy_id'], ['vacancy.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_vacancy_event_vacancy_created', 'vacancy_event', ['vacancy_id', 'created_at'], unique=False)
    op.create_table('screening',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('application_id', sa.Integer(), nullable=False),
    sa.Column('from_us', sa.Boolean(), nullable=False),
    sa.Column('text', sa.String(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['application.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_screening_position', 'screening', ['application_id', 'position'], unique=True)
    op.create_table('vacancy_status_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('vacancy_id', sa.Integer(), nullable=False),
    sa.Column('message_id', sa.Integer(), nullable=True),
    sa.Column('previous_status', sa.Enum('New', 'Applied', 'Answered', 'Test', 'Invitation', 'In Progress', 'Decline', 'Ghosting', 'Scam', 'Not Fit', 'Offer', name='vacancy_status'), nullable=True),
    sa.Column('status', sa.Enum('New', 'Applied', 'Answered', 'Test', 'Invitation', 'In Progress', 'Decline', 'Ghosting', 'Scam', 'Not Fit', 'Offer', name='vacancy_status'), nullable=False),
    sa.Column('explanation', sa.String(), nullable=True),
    sa.Column('applied', sa.Boolean(), server_default=sa.text('1'), nullable=False),
    sa.Column('source', sa.Enum('system', 'user', name='status_history_source'), server_default=sa.text("'system'"), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['message.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['vacancy_id'], ['vacancy.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_vsh_status', 'vacancy_status_history', ['status'], unique=False)
    op.create_index('ix_vsh_vacancy_changed', 'vacancy_status_history', ['vacancy_id', 'changed_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_vsh_vacancy_changed', table_name='vacancy_status_history')
    op.drop_index('ix_vsh_status', table_name='vacancy_status_history')
    op.drop_table('vacancy_status_history')
    op.drop_index('uq_screening_position', table_name='screening')
    op.drop_table('screening')
    op.drop_index('ix_vacancy_event_vacancy_created', table_name='vacancy_event')
    op.drop_table('vacancy_event')
    op.drop_index('uq_vacancy_contact_key', table_name='vacancy_contact')
    op.drop_index('ix_vacancy_contact_match_key', table_name='vacancy_contact')
    op.drop_table('vacancy_contact')
    op.drop_table('profile_project_skills')
    op.drop_table('profile_experience_skills')
    op.drop_index('ix_message_vacancy_id', table_name='message')
    op.drop_table('message')
    op.drop_index('ix_application_vacancy_id', table_name='application')
    op.drop_table('application')
    op.drop_index('uq_vacancy_aggregator_key', table_name='vacancy')
    op.drop_index('ix_vacancy_hr_id_is_parsed', table_name='vacancy')
    op.drop_index('ix_vacancy_company_id_is_parsed', table_name='vacancy')
    op.drop_table('vacancy')
    op.drop_index('ix_trash_event_channel_created', table_name='trash_event')
    op.drop_index('ix_trash_event_aggregator_key', table_name='trash_event')
    op.drop_table('trash_event')
    op.drop_table('profile_skills')
    op.drop_table('profile_project')
    op.drop_table('profile_language')
    op.drop_table('profile_experience')
    op.drop_index('uq_aggregator_resume_url', table_name='aggregator_resume')
    op.drop_index('uq_aggregator_resume_chosen', table_name='aggregator_resume', postgresql_where=sa.text('is_chosen'), sqlite_where=sa.text('is_chosen'))
    op.drop_table('aggregator_resume')
    op.drop_table('tg_account')
    op.drop_table('telegram_channel')
    op.drop_table('profile')
    op.drop_table('mail_account')
    op.drop_table('llm_config')
    op.drop_index('uq_hr_telegram_user_id', table_name='hr', postgresql_where=sa.text('telegram_user_id IS NOT NULL'), sqlite_where=sa.text('telegram_user_id IS NOT NULL'))
    op.drop_table('hr')
    op.drop_table('company')
    op.drop_table('bot_state')
    op.drop_table('blacklist')
    op.drop_table('app_settings')
    op.drop_index('uq_aggregator_host', table_name='aggregator')
    op.drop_table('aggregator')
