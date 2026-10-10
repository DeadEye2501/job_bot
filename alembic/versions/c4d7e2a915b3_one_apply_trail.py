"""one apply trail

Revision ID: c4d7e2a915b3
Revises: a9c3e1f07b42
Create Date: 2026-10-10 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c4d7e2a915b3'
down_revision: Union[str, Sequence[str], None] = 'a9c3e1f07b42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Роды ленты, которых больше никто не пишет: попытки автоотправки, провалы
# способов и закрытые вакансии остаются в журнале, а не в ленте карточки.
_GONE_KINDS = ('auto_send', 'apply_failed', 'vacancy_closed', 'applied_sent')


def upgrade() -> None:
    op.execute("UPDATE vacancy_event SET kind = 'applied' WHERE kind = 'applied_elsewhere'")
    gone = ", ".join(f"'{kind}'" for kind in _GONE_KINDS)
    op.execute(f"DELETE FROM vacancy_event WHERE kind IN ({gone})")


def downgrade() -> None:
    op.execute("UPDATE vacancy_event SET kind = 'applied_elsewhere' WHERE kind = 'applied'")
