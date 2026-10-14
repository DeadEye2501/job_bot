"""Следствия действий над вакансией, которым нужен поднятый бот.

Предмет — то, что мост делает чужими руками: ручной прогон каналов, повторный
разбор, отклик выбранным способом и удаление вместе с кэшем. Бот подделан:
внутрь его Telegram и модели мост не заходит ни разу, он зовёт его методы и
смотрит на ответ.
"""

import pytest

from tests.dbio import put
from tests.factories import vacancy_row
from tests.factories_aggregators import mail_account_row, vacancy_contact_row


@pytest.fixture
def mailable_vacancy(session_factory):
    """Вакансия с адресом HR и настроенной почтой: письмо — доступный способ."""

    async def _put():
        vacancy = vacancy_row()
        await put(session_factory, vacancy, mail_account_row())
        await put(session_factory, vacancy_contact_row(vacancy.id, "hr@company.test"))
        return vacancy

    return _put


@pytest.fixture
def broken_vacancy(with_bot, mailable_vacancy):
    """Вакансия, отклик по которой срывается броском изнутри бота."""

    async def _put():
        async def broken(vacancy_id, way):
            raise RuntimeError("сорвалось на полпути")

        with_bot().apply_chosen_way = broken
        return await mailable_vacancy()

    return _put


def _by_mail(vacancy) -> dict:
    return {"vacancy_id": vacancy.id, "method": "email", "target": "hr@company.test"}


async def test_a_manual_run_before_the_bot_is_up_is_refused_by_name(api, ask):
    """До входа в Telegram ручной прогон отбивают словами про бота.

    Кнопку рисуют всегда, а бота поднимают после входа. Прежде на эту кнопку
    мост молчал; молчания на дороге возврата нет — оно оставило бы кнопку
    нажатой навсегда, — и вместо него человеку говорят, чего не хватает.
    """
    answer = await ask(api.system.run_now)

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Бот ещё не готов"


async def test_a_busy_run_is_explained_not_swallowed(api, ask, with_bot, told):
    """Занятый прогон объясняют словами.

    Иначе человек жмёт кнопку, ничего не происходит, и он жмёт её снова —
    так и не узнав, что цикл уже идёт.
    """
    with_bot(poll="busy")

    answer = await ask(api.system.run_now)

    assert answer["ok"]["started"] is True
    assert await told() == {
        "message": "Уже идёт другой цикл, попробуйте позже",
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
    # Весть звучит, когда пройден весь оборот: каналы, агрегаторы и отклики
    # идут одной задачей.
    assert await told() == {"message": "Обход завершён", "danger": False}


async def test_a_stop_reaches_the_bot(api, ask, with_bot):
    """Остановка доходит до бота, а не гаснет в мосте.

    Показать её человеку нечем — об остановке он узнаёт по тому, что прогон
    кончился. Пропади вызов, кнопка стала бы украшением.
    """
    bot = with_bot()

    answer = await ask(api.system.stop_run)

    assert "ok" in answer
    assert ("cancel_current_poll",) in bot.calls


async def test_apply_all_before_the_bot_is_up_is_refused_by_name(api, ask):
    answer = await ask(api.system.apply_all_new)

    assert (answer["fail"], answer["detail"]) == ("denied", "Бот ещё не готов")


async def test_apply_all_reaches_the_bot_and_says_when_finished(api, ask, with_bot, told):
    bot = with_bot()

    answer = await ask(api.system.apply_all_new)

    assert answer["ok"] == {"started": True, "action": "apply_all_new"}
    assert await told() == {"message": "Отклики на новые вакансии закончены", "danger": False}
    assert ("apply_all_new",) in bot.calls


async def test_apply_all_stopped_by_a_missing_resume_asks_to_refresh_the_list(api, ask, with_bot, told):
    with_bot(apply_all="resume_missing")

    await ask(api.system.apply_all_new)

    assert await told() == {
        "message": "Выбранное резюме не найдено на сайте — обновите список резюме", "danger": True,
    }


async def test_a_stopped_apply_all_says_its_own_words(api, ask, with_bot, told):
    """Слова остановки свои, а не обхода: «Поллинг отменён» после «Стопа» на
    откликах сбил бы с толку."""
    with_bot(apply_all="cancelled")

    await ask(api.system.apply_all_new)

    assert await told() == {"message": "Отклики на новые вакансии остановлены", "danger": True}


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
    assert answer["detail"] == "Бот ещё не готов"


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
        "message": "У вакансии нет исходного текста — разбирать нечего",
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
    assert said["message"] == "Модель не ответила — разбор не состоялся, см. логи"


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
    assert await told() == {"message": "Вакансия разобрана заново", "danger": False}


async def test_a_refused_application_is_told_in_human_words(
    api, ask, with_bot, told, mailable_vacancy
):
    """Исход отклика переводят с кода на человеческий: покажи мост код — человек
    не понял бы, что делать дальше."""
    with_bot(apply_via="failed")
    vacancy = await mailable_vacancy()

    await ask(api.vacancies.apply_via, _by_mail(vacancy))

    assert await told() == {
        "message": "Отклик не состоялся — причина в журнале",
        "danger": True,
    }


async def test_an_unknown_refusal_code_still_reaches_the_window(
    api, ask, with_bot, told, mailable_vacancy
):
    """Незнакомый код отказа не теряется: человек слышит общий отказ.

    Коды заводит бэкенд, и новый появится там раньше, чем перевод здесь.
    Промолчи мост о незнакомом — отклик выглядел бы удавшимся.
    """
    with_bot(apply_via="квота_кончилась")
    vacancy = await mailable_vacancy()

    await ask(api.vacancies.apply_via, _by_mail(vacancy))

    assert await told() == {
        "message": "Не удалось откликнуться — см. логи",
        "danger": True,
    }


async def test_an_application_answers_before_it_is_done(
    api, ask, with_bot, told, mailable_vacancy
):
    """Ответ приходит сразу, а «записан» — вестью, когда отклик состоялся.

    Письмо сочиняет модель, а форму проходит агент, и ждать их значило бы
    держать окно.
    """
    with_bot()
    vacancy = await mailable_vacancy()

    answer = await ask(api.vacancies.apply_via, _by_mail(vacancy))

    assert answer["ok"] == {
        "started": True,
        "vacancy_id": vacancy.id,
        "action": "apply_via",
    }
    assert await told() == {"message": "Отклик записан", "danger": False}


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
    остался бы с «откликается» навсегда, ровно с той бедой, ради которой
    вести и заведены.
    """
    vacancy = await broken_vacancy()

    with caplog.at_level("ERROR"):
        answer = await ask(api.vacancies.apply_via, _by_mail(vacancy))
        said = await told()

    assert answer["ok"]["started"] is True
    assert said == {"message": "Не удалось откликнуться — см. логи", "danger": True}
    assert "сорвалось на полпути" in caplog.text
