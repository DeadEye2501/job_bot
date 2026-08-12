"""Следствия оповещений окна из конвейера.

Обход каналов идёт полтора часа. Всё это время окно должно показывать
происходящее: долю сделанного в нижней полосе, свежие вакансии в списке,
новых HR и компании во вкладке «Контакты». Иначе пользователь видит
замерший экран и решает, что приложение повисло.

Предмет здесь — что именно уходит в окно: какой из крючков дёрнут и с какими
доводами. Отсутствие подписчика и проглоченная поломка сюда не входят: у
методов конвейера тело — одна строка `fire(...)`, и обе ветки принадлежат
самому оповещению (`tests/backend/test_notify.py`).
"""

import pytest


@pytest.mark.parametrize(
    ("fire", "hook"),
    [
        pytest.param("_fire_contacts_changed", "on_contacts_changed", id="контакты"),
        pytest.param("_fire_vacancies_changed", "on_vacancies_changed", id="вакансии"),
    ],
)
async def test_the_window_is_told_what_changed(make_pipeline, fire, hook):
    """Окно узнаёт об изменившемся и перечитывает свой список."""
    pipeline = await make_pipeline()
    heard: list[int] = []
    setattr(pipeline, hook, lambda: heard.append(1))

    getattr(pipeline, fire)()

    assert heard == [1]


async def test_the_window_hears_how_much_is_done(make_pipeline):
    """Окно узнаёт долю сделанного: что за шаг, где идёт и сколько всего."""
    pipeline = await make_pipeline()
    heard: list[tuple] = []
    pipeline.on_progress = lambda *args: heard.append(args)

    pipeline._emit_progress("channel", "@pyjobs", 3, 18)

    assert heard == [("channel", "@pyjobs", 3, 18)]
