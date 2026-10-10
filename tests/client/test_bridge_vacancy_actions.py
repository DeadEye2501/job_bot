"""Следствия действий над вакансией, которым нужен поднятый бот.

Предмет — то, что мост делает чужими руками: ручной прогон каналов, повторный
разбор, отправка отклика и удаление вместе с кэшем. Бот подделан: внутрь его
Telegram и модели мост не заходит ни разу, он зовёт пять методов и смотрит на
ответ.
"""

import pytest

from tests.dbio import put
from tests.factories import vacancy_row


@pytest.fixture
def broken_vacancy(session_factory, with_bot):
    """Вакансия, отправка по которой срывается броском изнутри бота."""

    async def _put():
        async def broken(vacancy_id):
            raise RuntimeError("сорвалось на полпути")

        with_bot().ui_send_vacancy_application = broken
        vacancy = vacancy_row()
        await put(session_factory, vacancy)
        return vacancy

    return _put


async def test_a_manual_run_before_the_bot_is_up_is_refused_by_name(api, ask):
    """До входа в Telegram ручной прогон отбивают словами про бота.

    Кнопку рисуют всегда, а бота поднимают после входа. Прежде на эту кнопку
    мост молчал; молчания на дороге возврата нет — оно оставило бы кнопку
    нажатой навсегда, — и вместо него человеку говорят, чего не хватает.
    """
    answer = await ask(api.system.run_now)

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Бот ещё не готов."


async def test_a_busy_run_is_explained_not_swallowed(api, ask, with_bot, told):
    """Занятый прогон объясняют словами.

    Иначе человек жмёт кнопку, ничего не происходит, и он жмёт её снова —
    так и не узнав, что цикл уже идёт.
    """
    with_bot(poll="busy")

    answer = await ask(api.system.run_now)

    assert answer["ok"]["started"] is True
    assert await told() == {
        "message": "Уже идёт другой цикл, попробуйте позже.",
        "danger": True,
    }


async def test_a_finished_run_says_so_when_it_is_finished(api, ask, with_bot, told):
    """Обход отвечает сразу, а исход говорит вестью.

    Обход идёт по всем каналам и по всем их новым постам — самая долгая работа
    в приложении. Дождись мост её конца, окно висело бы десятками минут.
    """
    with_bot()

    answer = await ask(api.system.run_now)

    assert answer["ok"] == {"started": True, "action": "run_now"}
    # Весть звучит, когда пройдены каналы: обход агрегаторов уходит дальше
    # отдельной задачей, и «обход закончен» в этот миг было бы неправдой.
    assert await told() == {"message": "Каналы пройдены.", "danger": False}


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
    api, ask, with_bot, told, session_factory
):
    """Неудавшийся разбор называет причину: разбирать было нечего.

    У вакансии, заведённой руками, исходного текста нет, и повторный разбор
    для неё бессмыслен. Прежде тем же ответом объяснялись все шесть исходов —
    и молчащая модель, и занятое место, — и человек шёл искать запись, которая
    на месте.
    """
    with_bot(rerun="no_text")
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    await ask(api.vacancies.rerun, {"vacancy_id": vacancy.id})

    assert await told() == {
        "message": "У вакансии нет исходного текста — разбирать нечего.",
        "danger": True,
    }


async def test_a_rerun_the_model_slept_through_says_that_instead(
    api, ask, with_bot, told, session_factory
):
    """Молчание модели называют молчанием модели, а не пропажей вакансии."""
    with_bot(rerun="llm")
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    await ask(api.vacancies.rerun, {"vacancy_id": vacancy.id})

    said = await told()
    assert said["message"] == "Модель не ответила — разбор не состоялся, см. логи."


async def test_a_rerun_answers_before_it_parses(
    api, ask, with_bot, told, session_factory
):
    """Ответ приходит сразу, а исход — вестью, когда разбор кончится.

    Разбор одной вакансии — это от двух до пяти обращений к модели. Дождись
    мост его конца, окно висело бы всё это время.
    """
    with_bot()
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(api.vacancies.rerun, {"vacancy_id": vacancy.id})

    assert answer["ok"] == {
        "started": True,
        "vacancy_id": vacancy.id,
        "action": "rerun",
    }
    assert await told() == {"message": "Вакансия разобрана заново.", "danger": False}


async def test_a_refused_application_is_told_in_human_words(
    api, ask, with_bot, told, session_factory
):
    """Отказ отправки переводят с кода на человеческий.

    Причин девять, и они разные по смыслу: непривязанный HR чинится нажатием,
    а пустая анкета — заполнением. Покажи мост код — человек не понял бы, что
    делать дальше.
    """
    with_bot(application=(False, "no_hr"))
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    await ask(api.vacancies.send_application, {"vacancy_id": vacancy.id})

    assert await told() == {
        "message": "К вакансии не привязан HR.",
        "danger": True,
    }


async def test_an_unknown_refusal_code_still_reaches_the_window(
    api, ask, with_bot, told, session_factory
):
    """Незнакомый код отказа не теряется: человек слышит общий отказ.

    Коды заводит бэкенд, и новый появится там раньше, чем перевод здесь.
    Промолчи мост о незнакомом — отправка выглядела бы удавшейся.
    """
    with_bot(application=(False, "квота_кончилась"))
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    await ask(api.vacancies.send_application, {"vacancy_id": vacancy.id})

    assert await told() == {
        "message": "Не удалось отправить отклик — см. логи.",
        "danger": True,
    }


async def test_a_sent_application_answers_before_it_sends(
    api, ask, with_bot, told, session_factory
):
    """Ответ приходит сразу, а «отправлено» — вестью, когда письмо ушло.

    Письмо сочиняет модель, и ждать её значило бы держать окно; отменить
    начатую отправку это всё равно не отменило бы.
    """
    with_bot()
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(api.vacancies.send_application, {"vacancy_id": vacancy.id})

    assert answer["ok"] == {
        "started": True,
        "vacancy_id": vacancy.id,
        "action": "send",
    }
    assert await told() == {"message": "Отклик отправлен.", "danger": False}


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


async def test_a_launched_job_that_broke_still_answers_the_window(
    api, ask, told, broken_vacancy, caplog
):
    """Сорвавшаяся пущенная работа всё равно говорит окну, и след ложится в журнал.

    Ответ на зов сказал только «пущено»: промолчи мост об исходе — человек
    остался бы с «отправляется» навсегда, ровно с той бедой, ради которой
    вести и заведены.
    """
    vacancy = await broken_vacancy()

    with caplog.at_level("ERROR"):
        answer = await ask(api.vacancies.send_application, {"vacancy_id": vacancy.id})
        said = await told()

    assert answer["ok"]["started"] is True
    assert said == {"message": "Не удалось отправить отклик — см. логи.", "danger": True}
    assert "сорвалось на полпути" in caplog.text
