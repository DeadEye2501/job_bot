"""Следствия действий над вакансией, которым нужен поднятый бот.

Предмет — то, что мост делает чужими руками: ручной прогон каналов, повторный
разбор, отправка отклика и удаление вместе с кэшем. Бот подделан: внутрь его
Telegram и модели мост не заходит ни разу, он зовёт пять методов и смотрит на
ответ.
"""

import json

import pytest

from tests.dbio import put
from tests.factories import vacancy_row
from tests.fakes.ui_bot import UiBot


@pytest.fixture
def with_bot(main_api):
    """Ставит подделку бота на место настоящего и отдаёт её же."""

    def _put(**answers) -> UiBot:
        bot = UiBot(**answers)
        main_api._bot = bot
        return bot

    return _put


async def test_a_manual_run_before_the_bot_is_up_says_nothing(main_api, watch):
    """До входа в Telegram ручной прогон молчит, а не отвечает отказом.

    Кнопку рисуют всегда, а бота поднимают после входа. Ответь мост отказом —
    человек, ещё не вошедший, получал бы на неё сообщение о поломке.
    """
    caught = watch(main_api.ingestion_action_done)

    main_api.trigger_ingestion()

    assert await caught.silent()


async def test_a_busy_run_is_explained_not_swallowed(main_api, watch, with_bot):
    """Занятый прогон объясняют словами.

    Иначе человек жмёт кнопку, ничего не происходит, и он жмёт её снова —
    так и не узнав, что цикл уже идёт.
    """
    caught = watch(main_api.ingestion_action_done)
    with_bot(poll="busy")

    main_api.trigger_ingestion()

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["status"] == "busy"


async def test_a_stop_reaches_the_bot(main_api, with_bot):
    """Остановка доходит до бота, а не гаснет в мосте.

    Ответа у этой кнопки нет вовсе — окно узнаёт об остановке по тому, что
    прогон кончился. Пропади вызов, кнопка стала бы украшением.
    """
    bot = with_bot()

    main_api.stop_ingestion()

    assert ("cancel_current_poll",) in bot.calls


async def test_a_rerun_before_the_bot_is_up_is_refused_by_name(
    main_api, watch, session_factory
):
    """Повторный разбор без бота отбивают словами про бота.

    Разбор идёт через Telegram и модель — без них он невозможен, и человеку
    надо сказать, чего именно не хватает, а не «не получилось».
    """
    caught = watch(main_api.vacancy_action_done)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.rerun_vacancy_pipeline(json.dumps({"vacancy_id": vacancy.id}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Бот ещё не готов."


async def test_a_rerun_that_had_nothing_to_parse_says_so(
    main_api, watch, with_bot, session_factory
):
    """Неудавшийся разбор называет причину: разбирать было нечего.

    У вакансии, заведённой руками, исходного текста нет, и повторный разбор
    для неё бессмыслен. Без внятного ответа кнопка выглядела бы сломанной.
    """
    caught = watch(main_api.vacancy_action_done)
    with_bot(rerun=False)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.rerun_vacancy_pipeline(json.dumps({"vacancy_id": vacancy.id}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["action"] == "rerun"
    assert "raw_text" in answer["error"]


async def test_a_refused_application_is_told_in_human_words(
    main_api, watch, with_bot, session_factory
):
    """Отказ отправки переводят с кода на человеческий.

    Причин девять, и они разные по смыслу: непривязанный HR чинится нажатием,
    а пустая анкета — заполнением. Покажи мост код — человек не понял бы, что
    делать дальше.
    """
    caught = watch(main_api.vacancy_action_done)
    with_bot(application=(False, "no_hr"))
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.send_vacancy_application(json.dumps({"vacancy_id": vacancy.id}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "К вакансии не привязан HR."


async def test_an_unknown_refusal_code_still_reaches_the_window(
    main_api, watch, with_bot, session_factory
):
    """Незнакомый код отказа не теряется, а доезжает как есть.

    Коды заводит бэкенд, и новый появится там раньше, чем перевод здесь.
    Промолчи мост о незнакомом — отправка выглядела бы удавшейся.
    """
    caught = watch(main_api.vacancy_action_done)
    with_bot(application=(False, "квота_кончилась"))
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.send_vacancy_application(json.dumps({"vacancy_id": vacancy.id}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert "квота_кончилась" in answer["error"]


async def test_a_sent_application_names_the_reason_of_success(
    main_api, watch, with_bot, session_factory
):
    """Удачная отправка тоже называет свой код.

    По нему окно отличает обычную отправку от той, о которой надо сказать
    отдельно, — на будущие коды это единственная зацепка.
    """
    caught = watch(main_api.vacancy_action_done)
    with_bot()
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.send_vacancy_application(json.dumps({"vacancy_id": vacancy.id}))

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["reason"] == "sent"


async def test_deleting_with_the_bot_up_goes_through_the_bot(
    main_api, watch, with_bot, session_factory
):
    """При поднятом боте удаление идёт его дорогой, а не мимо.

    Мимо бота вакансия исчезла бы из базы, но осталась бы в кэше векторов —
    и продолжила бы влиять на отбор похожих, которых уже нет.
    """
    caught = watch(main_api.vacancy_action_done)
    bot = with_bot()
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.delete_vacancy(json.dumps({"vacancy_id": vacancy.id}))

    assert (await caught.next())["ok"] is True
    assert ("ui_forget_vacancy", vacancy.id) in bot.calls
