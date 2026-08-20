"""Следы, которые оставляет ушедший отклик.

Их три, и каждый нужен своему месту в окне: сообщение — переписке с HR,
смена статуса с записью в истории — карточке вакансии, отметка «отклик
отправлен» — её ленте. Первого при заглушенной отправке не появляется
нарочно: письма в Telegram нет, и показывать его в переписке значило бы
обещать пользователю то, чего HR не получал.

Ушедшее письмо назад не вернуть, поэтому отправка считается состоявшейся,
даже если запись о ней не удалась. Тогда статус переставляется отдельно —
без него повторная отправка ушла бы вторым письмом тому же HR.
"""

import pytest

from backend.models import (
    BotMode,
    Message,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
    VacancyStatusHistory,
)
from tests.dbio import all_rows, only_row
from tests.factories import hr_row


async def test_a_letter_reaches_the_address_the_hr_carries(
    ready_to_send, outbox
):
    """Письмо уходит по адресу, записанному у HR."""
    bot, hr, vacancy = await ready_to_send()

    assert await bot.send(hr, "письмо", vacancy_id=vacancy.id) is True
    assert outbox.sent == [("maria", "письмо", None)]


async def test_a_numeric_address_wins_over_a_name(ready_to_send, outbox):
    """Номер собеседника перевешивает имя.

    Имя пользователь Telegram меняет когда захочет, а номер остаётся —
    по нему письмо дойдёт и после переименования.
    """
    bot, hr, _ = await ready_to_send(hr=hr_row(telegram_user_id=777))

    await bot.send(hr, "письмо")

    assert outbox.sent == [(777, "письмо", None)]


async def test_a_sent_letter_shows_up_in_the_chat(ready_to_send, session_factory, outbox):
    """Ушедшее письмо появляется в переписке с HR.

    Номер сообщения запоминается тот, что вернул Telegram: по нему потом
    опознаётся отметка о прочтении.
    """
    bot, hr, vacancy = await ready_to_send()

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    saved = await only_row(session_factory, Message)
    assert saved.is_incoming is False
    assert saved.hr_id == hr.id
    assert saved.vacancy_id == vacancy.id
    assert saved.text == "письмо"
    assert saved.tg_message_id == outbox.assigned_id


async def test_a_suppressed_letter_stays_out_of_the_chat(ready_to_send, session_factory):
    """Заглушенное письмо в переписке не показывается.

    В Telegram его нет; строка в переписке была бы обещанием того, чего
    HR не получал.
    """
    bot, hr, vacancy = await ready_to_send()

    assert await bot.send(hr, "письмо", vacancy_id=vacancy.id) is True
    assert await all_rows(session_factory, Message) == []


async def test_a_sent_letter_moves_the_vacancy_to_applied(
    ready_to_send, session_factory, outbox
):
    """Ушедшее письмо переводит вакансию в «отклик отправлен»."""
    bot, hr, vacancy = await ready_to_send()

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED


async def test_the_move_lands_in_the_vacancy_timeline(
    ready_to_send, session_factory, outbox
):
    """Смена статуса попадает в историю вакансии.

    Без записи переход выглядел бы в ленте молчанием: пользователь видел
    бы новый цвет статуса и ни строки о том, откуда он взялся.
    """
    bot, hr, vacancy = await ready_to_send()

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    step = await only_row(session_factory, VacancyStatusHistory)
    assert step.previous_status is VacancyStatus.NEW
    assert step.status is VacancyStatus.APPLIED
    assert step.applied is True


@pytest.mark.parametrize(
    ("force", "expected"),
    [
        pytest.param(True, "Ручная отправка.", id="из окна"),
        pytest.param(False, "Авто-отправка отклика.", id="сама"),
    ],
)
async def test_the_timeline_says_who_sent_the_letter(
    ready_to_send, session_factory, outbox, force, expected
):
    """История называет, кто отправил письмо — пользователь или бот."""
    bot, hr, vacancy = await ready_to_send()

    await bot.send(hr, "письмо", vacancy_id=vacancy.id, force=force)

    step = await only_row(session_factory, VacancyStatusHistory)
    assert step.explanation == expected


async def test_a_letter_without_a_vacancy_moves_nothing(
    ready_to_send, session_factory, outbox
):
    """Письмо не про вакансию ничьего статуса не трогает."""
    bot, hr, vacancy = await ready_to_send()

    assert await bot.send(hr, "письмо") is True

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NEW
    assert await all_rows(session_factory, VacancyStatusHistory) == []
    assert await all_rows(session_factory, VacancyEvent) == []


async def test_a_vacancy_already_past_applied_keeps_its_status(
    ready_to_send, session_factory, outbox
):
    """Вакансия, ушедшая дальше отклика, назад не откатывается.

    Приглашение — состояние более позднее; вернуть его к «отклик
    отправлен» значило бы потерять то, что пользователь уже знает.
    """
    bot, hr, vacancy = await ready_to_send(
        status=VacancyStatus.INVITATION
    )

    assert await bot.send(hr, "письмо", vacancy_id=vacancy.id) is True

    assert (
        await only_row(session_factory, Vacancy)
    ).status is VacancyStatus.INVITATION
    assert await all_rows(session_factory, VacancyStatusHistory) == []


async def test_a_manual_send_lifts_a_vacancy_out_of_not_fit(
    ready_to_send, session_factory, outbox
):
    """Отправка из окна поднимает вакансию из «не подходит».

    Отбраковку ставит машина, и пользователь вправе с ней не
    согласиться: раз он нажал «отправить», отклик состоялся.
    """
    bot, hr, vacancy = await ready_to_send(
        status=VacancyStatus.NOT_FIT
    )

    await bot.send(hr, "письмо", vacancy_id=vacancy.id, force=True)

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED


async def test_a_manual_send_moves_even_a_later_status(
    ready_to_send, session_factory, outbox
):
    """Отправка из окна переводит в «отклик отправлен» и с позднего статуса.

    Письмо HR ушло, и статус обязан это показать. Прежде вакансия оставалась
    в приглашении, а в истории не появлялось ни строки — нажимать можно было
    сколько угодно раз, и каждое нажатие писало HR заново.
    """
    bot, hr, vacancy = await ready_to_send(
        status=VacancyStatus.INVITATION
    )

    await bot.send(hr, "письмо", vacancy_id=vacancy.id, force=True)

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED
    written = await only_row(session_factory, VacancyStatusHistory)
    assert written.previous_status is VacancyStatus.INVITATION
    assert written.status is VacancyStatus.APPLIED
    assert written.applied is True


async def test_the_timeline_records_that_an_application_went_out(
    ready_to_send, session_factory, outbox
):
    """В ленте вакансии остаётся отметка об отправленном отклике.

    Она нужна отдельно от смены статуса: статус меняется и по ответу HR,
    а эта отметка говорит именно об исходящем письме.
    """
    bot, hr, vacancy = await ready_to_send()

    await bot.send(hr, "письмо", vacancy_id=vacancy.id, force=True)

    event = await only_row(session_factory, VacancyEvent)
    assert event.kind == "applied_sent"
    assert event.payload == {
        "hr_id": hr.id,
        "force": True,
        "suppressed": False,
        "cover_letter_chars": len("письмо"),
        "tg_message_id": outbox.assigned_id,
    }


async def test_a_suppressed_application_still_counts(
    ready_to_send, session_factory
):
    """Заглушенный замком отклик всё равно засчитывается вакансии.

    Иначе обход с включённой «симуляцией отправки» слал бы отклик по одной и
    той же вакансии на каждом обороте цикла — а прогонять сбор, не беспокоя
    живых HR, надо уметь. Строки переписки при этом нет: письма никто не
    получал.

    Красной фазы не было: проверка вернулась взамен снесённой вместе с
    «тестовым режимом» и сторожит то же следствие с другого замка. Доверие
    заслужит итоговым проходом.
    """
    bot, hr, vacancy = await ready_to_send()

    assert await bot.send(hr, "письмо", vacancy_id=vacancy.id) is True

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED
    assert await all_rows(session_factory, Message) == []


async def test_a_suppressed_send_is_marked_as_such_in_the_timeline(
    ready_to_send, session_factory
):
    """Заглушенная отправка помечена в ленте как заглушенная.

    Иначе разработчик не отличил бы прогон без настоящей отправки от
    настоящего: сообщения в переписке нет ни там, ни там.
    """
    bot, hr, vacancy = await ready_to_send()

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    event = await only_row(session_factory, VacancyEvent)
    assert event.payload["suppressed"] is True
    assert event.payload["tg_message_id"] is None


async def test_a_send_tells_the_window_the_vacancy_changed(
    ready_to_send, outbox
):
    """Об ушедшем письме окно узнаёт вестью, и другого способа у него нет.

    Зов, которым отправку завели, ответил «пущено» задолго до того, как модель
    сочинила письмо: не пошли мы весть — карточка так и стояла бы с прежним
    статусом, пока человек не переключится на соседнюю и обратно.
    """
    bot, hr, vacancy = await ready_to_send()
    heard = []
    bot.on_vacancies_changed = lambda: heard.append("вакансии")

    await bot.send(hr, "письмо", vacancy_id=vacancy.id, force=True)

    assert heard == ["вакансии"]


async def test_a_simulated_send_tells_the_window_too(
    ready_to_send
):
    """Заглушённая отправка окну тоже рассказывает: статус-то она переставила.

    Замок отправки стенд держит взведённым, и снимать его здесь нечем: предмет
    как раз в том, что весть уходит и без настоящего письма.
    """
    bot, hr, vacancy = await ready_to_send()
    heard = []
    bot.on_vacancies_changed = lambda: heard.append("вакансии")

    await bot.send(hr, "письмо", vacancy_id=vacancy.id, force=True)

    assert heard == ["вакансии"]


async def test_a_refused_send_tells_the_window_nothing(
    ready_to_send, outbox
):
    """Отказ заслона вестью не сопровождается: менять окну нечего."""
    bot, hr, vacancy = await ready_to_send(mode=BotMode.OFF)
    heard = []
    bot.on_vacancies_changed = lambda: heard.append("вакансии")

    assert await bot.send(hr, "письмо", vacancy_id=vacancy.id, force=True) is False

    assert heard == []
