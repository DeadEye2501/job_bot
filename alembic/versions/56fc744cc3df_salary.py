"""salary

Зарплата: минимальная рядом с желаемой, валюта и период анкеты заданы всегда,
период у вилки новых вакансий и кэш курсов валют, заполненный сразу.

Revision ID: 56fc744cc3df
Revises: f2e88ee2a3a6
Create Date: 2026-11-12 12:00:00.000000+00:00

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '56fc744cc3df'
down_revision: Union[str, Sequence[str], None] = 'f2e88ee2a3a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERIOD = sa.Enum('hour', 'month', 'year', name='salary_period')

# Курсы open.er-api.com на 12.11.2026, за 1 USD: кэш пустым не бывает, и
# расчёту зарплаты не нужна ветка «курса нет».
_FETCHED_AT = datetime(2026, 11, 12, 0, 2, 31)
_RATES = {
    'USD': 1.0, 'RUB': 82.742974, 'EUR': 0.899865,
    'AMD': 360.646084, 'KZT': 446.086013, 'GEL': 2.594131,
}


def upgrade() -> None:
    # Пересборка `profile` при включённых ключах упирается в ссылающиеся на неё
    # строки (`test_migration_engine.py`); гасится до первой записи.
    op.execute("PRAGMA foreign_keys=OFF")
    rates = op.create_table('currency_rate',
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('per_usd', sa.Float(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    op.bulk_insert(rates, [
        {'code': code, 'per_usd': per_usd, 'fetched_at': _FETCHED_AT}
        for code, per_usd in _RATES.items()
    ])
    # Старым вакансиям период не ставится: из «$30/hr» в базе лежит только 30,
    # и месяц назвал бы ставку в 168 раз меньше. Без периода расчёт называет
    # желаемую, а «Прогнать заново» спросит период у модели.
    op.add_column('vacancy', sa.Column('salary_period', _PERIOD, nullable=True))
    op.execute("UPDATE profile SET expected_salary_currency = '$' WHERE expected_salary_currency IS NULL")
    op.execute("UPDATE profile SET expected_salary_period = 'month' WHERE expected_salary_period IS NULL")
    with op.batch_alter_table('profile') as batch:
        batch.add_column(sa.Column('minimum_salary', sa.Integer(), nullable=True))
        batch.alter_column('expected_salary_currency', existing_type=sa.String(),
                           nullable=False, server_default='$')
        batch.alter_column('expected_salary_period', existing_type=_PERIOD,
                           nullable=False, server_default='month')


def downgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table('profile') as batch:
        batch.alter_column('expected_salary_period', existing_type=_PERIOD,
                           nullable=True, server_default=None)
        batch.alter_column('expected_salary_currency', existing_type=sa.String(),
                           nullable=True, server_default=None)
        batch.drop_column('minimum_salary')
    with op.batch_alter_table('vacancy') as batch:
        batch.drop_column('salary_period')
    op.drop_table('currency_rate')
