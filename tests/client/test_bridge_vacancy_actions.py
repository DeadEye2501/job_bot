"""Следствия действий над вакансией, которым нужен поднятый бот.

Предмет — то, что мост делает чужими руками: ручной прогон каналов, повторный
разбор, отправка отклика и удаление вместе с кэшем. Бот подделан: внутрь его
Telegram и модели мост не заходит ни разу, он зовёт пять методов и смотрит на
ответ.
"""

from tests.dbio import put
from tests.factories import vacancy_row


async def test_a_manual_run_before_the_bot_is_up_is_refused_by_name(api, ask):
    """До входа в Telegram ручной прогон отбивают словами про бота.

    Кнопку рисуют всегда, а бота поднимают после входа. Прежде на эту кнопку
    мост молчал; молчания на дороге возврата нет — оно оставило бы кнопку
    нажатой навсегда, — и вместо него человеку говорят, чего не хватает.
    """
    answer = await ask(api.system.run_now)

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Бот ещё не готов."


async def test_a_busy_run_is_explained_not_swallowed(api, ask, with_bot):
    """Занятый прогон объясняют словами.

    Иначе человек жмёт кнопку, ничего не происходит, и он жмёт её снова —
    так и не узнав, что цикл уже идёт.
    """
    with_bot(poll="busy")

    answer = await ask(api.system.run_now)

    assert answer["fail"] == "denied"
    assert answer["status"] == "busy"


async def test_a_stop_reaches_the_bot(api, ask, with_bot):
    """Остановка доходит до бота, а не гаснет в мосте.

    Показать её человеку нечем — об остановке он узнаёт по тому, что прогон
    кончился. Пропади вызов, кнопка стала бы украшением.
    """
    bot = with_bot()

    answer = await ask(api.system.stop_run)

    assert "ok" in answer
    assert ("cancel_current_poll",) in bot.calls


async def test_a_rerun_before_the_bot_is_up_is_refused_by_name(
    api, ask, session_factory
):
    """Повторный разбор без бота отбивают словами про бота.

    Разбор идёт через Telegram и модель — без них он невозможен, и человеку
    надо сказать, чего именно не хватает, а не «не получилось».
    """
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(api.vacancies.rerun, {"vacancy_id": vacancy.id})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Бот ещё не готов."


async def test_a_rerun_that_had_nothing_to_parse_says_so(
    api, ask, with_bot, session_factory
):
    """Неудавшийся разбор называет причину: разбирать было нечего.

    У вакансии, заведённой руками, исходного текста нет, и повторный разбор
    для неё бессмыслен. Без внятного ответа кнопка выглядела бы сломанной.
    """
    with_bot(rerun=False)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(api.vacancies.rerun, {"vacancy_id": vacancy.id})

    assert answer["fail"] == "denied"
    assert answer["action"] == "rerun"
    assert "raw_text" in answer["detail"]


async def test_a_refused_application_is_told_in_human_words(
    api, ask, with_bot, session_factory
):
    """Отказ отправки переводят с кода на человеческий.

    Причин девять, и они разные по смыслу: непривязанный HR чинится нажатием,
    а пустая анкета — заполнением. Покажи мост код — человек не понял бы, что
    делать дальше.
    """
    with_bot(application=(False, "no_hr"))
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(api.vacancies.send_application, {"vacancy_id": vacancy.id})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "К вакансии не привязан HR."


async def test_an_unknown_refusal_code_still_reaches_the_window(
    api, ask, with_bot, session_factory
):
    """Незнакомый код отказа не теряется, а доезжает как есть.

    Коды заводит бэкенд, и новый появится там раньше, чем перевод здесь.
    Промолчи мост о незнакомом — отправка выглядела бы удавшейся.
    """
    with_bot(application=(False, "квота_кончилась"))
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(api.vacancies.send_application, {"vacancy_id": vacancy.id})

    assert answer["fail"] == "denied"
    assert "квота_кончилась" in answer["detail"]


async def test_a_sent_application_names_the_reason_of_success(
    api, ask, with_bot, session_factory
):
    """Удачная отправка тоже называет свой код.

    По нему окно отличает обычную отправку от той, о которой надо сказать
    отдельно, — на будущие коды это единственная зацепка.
    """
    with_bot()
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(api.vacancies.send_application, {"vacancy_id": vacancy.id})

    assert "ok" in answer
    assert answer["ok"]["reason"] == "sent"


async def test_deleting_with_the_bot_up_goes_through_the_bot(
    api, ask, with_bot, session_factory
):
    """При поднятом боте удаление идёт его дорогой, а не мимо.

    Мимо бота вакансия исчезла бы из базы, но осталась бы в кэше векторов —
    и продолжила бы влиять на отбор похожих, которых уже нет.
    """
    bot = with_bot()
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(api.vacancies.delete, {"vacancy_id": vacancy.id})

    assert "ok" in answer
    assert ("ui_forget_vacancy", vacancy.id) in bot.calls
