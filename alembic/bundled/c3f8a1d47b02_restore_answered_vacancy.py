"""restore the answered vacancy (заглушка для сборки)

Настоящая восстановительная миграция с тем же номером лежит в
`alembic/versions/` и под версией не ходит: в ней личные данные — имя и аватар
настоящего HR, его telegram-id, тексты писем. В сборку она попадать не должна.

Заглушка нужна по тому же доводу, что и у засевной: каталог данных у сборки и у
исходников один, и номер ревизии, записанный в `alembic_version` запуском из
исходников, exe обязан находить в своей истории — иначе `upgrade head` при
старте бросает `CommandError`, а окна у сборки нет.

Revision ID: c3f8a1d47b02
Revises: aa4e0de05368
"""
from typing import Sequence, Union


revision: str = 'c3f8a1d47b02'
down_revision: Union[str, Sequence[str], None] = 'aa4e0de05368'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ничего: восстанавливается личная переписка, и в сборку она не едет."""


def downgrade() -> None:
    """Ничего: сносить нечего."""
