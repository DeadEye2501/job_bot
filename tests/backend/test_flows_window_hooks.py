"""Следствия оповещений окна из конвейера.

Обход каналов идёт полтора часа. Всё это время окно должно показывать
происходящее: долю сделанного в нижней полосе, свежие вакансии в списке,
новых HR и компании во вкладке «Контакты». Иначе пользователь видит
замерший экран и решает, что приложение повисло.

Подписан ли кто-то на оповещение — дело окна, а не конвейера: без окна бот
работает из командной строки, и оповещать там некого. Сломанное оповещение
работу тоже не отменяет: оно красит экран, а не собирает вакансии.
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


@pytest.mark.parametrize(
    "fire",
    [
        pytest.param("_fire_contacts_changed", id="контакты"),
        pytest.param("_fire_vacancies_changed", id="вакансии"),
    ],
)
async def test_without_a_window_there_is_nobody_to_tell(make_pipeline, fire):
    """Без окна оповещать некого, и конвейер не падает.

    Бот запускается и из командной строки — там подписчика нет вовсе.
    """
    pipeline = await make_pipeline()

    getattr(pipeline, fire)()


@pytest.mark.parametrize(
    ("fire", "hook"),
    [
        pytest.param("_fire_contacts_changed", "on_contacts_changed", id="контакты"),
        pytest.param("_fire_vacancies_changed", "on_vacancies_changed", id="вакансии"),
    ],
)
async def test_a_broken_window_hook_is_swallowed(make_pipeline, fire, hook):
    """Сломанное оповещение работу конвейера не прерывает.

    Оно красит экран, а не собирает вакансии; уронив из-за него обход,
    бот потерял бы полтора часа работы ради перерисовки списка.
    """
    pipeline = await make_pipeline()

    def broken():
        raise RuntimeError("окно")

    setattr(pipeline, hook, broken)

    getattr(pipeline, fire)()


async def test_the_window_hears_how_much_is_done(make_pipeline):
    """Окно узнаёт долю сделанного: что за шаг, где идёт и сколько всего."""
    pipeline = await make_pipeline()
    heard: list[tuple] = []
    pipeline.on_progress = lambda *args: heard.append(args)

    pipeline._emit_progress("channel", "@pyjobs", 3, 18)

    assert heard == [("channel", "@pyjobs", 3, 18)]


async def test_without_a_window_progress_goes_nowhere(make_pipeline):
    """Без окна долю сделанного сообщать некому, и конвейер не падает."""
    pipeline = await make_pipeline()

    pipeline._emit_progress("channel", "@pyjobs", 3, 18)


async def test_a_broken_progress_hook_is_swallowed(make_pipeline):
    """Сломанное оповещение о доле обход не прерывает."""
    pipeline = await make_pipeline()

    def broken(stage, label, current, total):
        raise RuntimeError("окно")

    pipeline.on_progress = broken

    pipeline._emit_progress("channel", "@pyjobs", 3, 18)
