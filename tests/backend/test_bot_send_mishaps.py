"""Что остаётся после отправки, пошедшей не так.

Беды разной природы. Telegram может отказать «слишком часто» — тогда письма
нет вовсе, и час запрета запоминается, чтобы автоматика не долбилась в
закрытую дверь. А может не удаться запись о письме, которое уже ушло, — и вот
это назад не отыграть: сообщение у HR есть.

Третий случай бедой только выглядит: строку письма успело положить эхо из
Telegram. Это штатная гонка, и путь обязан пройти до конца молча.

Во втором случае статус переставляется отдельной короткой сделкой. Запись о
письме потеряна, зато повторная отправка отобьётся проверкой «уже
откликались» — второе письмо тому же HR хуже дырки в истории.
"""

import logging
import time

from pyrogram.errors import FloodWait

from backend.models import (
    Message,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
    VacancyStatusHistory,
)
from tests.dbio import all_rows, only_row, put
from tests.factories import message_row


class _BrokenCommits:
    """Фабрика сессий, у которой первые несколько коммитов срываются."""

    def __init__(self, real, failures: int) -> None:
        self._real = real
        self.left = failures

    def __call__(self):
        return _BrokenScope(self._real(), self)


class _BrokenScope:
    """Область сессии, выдающая наружу сессию со срывающимся коммитом."""

    def __init__(self, scope, owner: _BrokenCommits) -> None:
        self._scope = scope
        self._owner = owner

    async def __aenter__(self):
        return _BrokenSession(await self._scope.__aenter__(), self._owner)

    async def __aexit__(self, *exc):
        return await self._scope.__aexit__(*exc)


class _BrokenSession:
    """Сессия, которая срывается на коммите, пока у хозяина есть срывы."""

    def __init__(self, session, owner: _BrokenCommits) -> None:
        self._session = session
        self._owner = owner

    def __getattr__(self, name):
        return getattr(self._session, name)

    async def commit(self):
        if self._owner.left > 0:
            self._owner.left -= 1
            raise OSError("диск отвалился")
        await self._session.commit()


async def test_a_rate_limited_send_is_not_counted(ready_to_send, session_factory, outbox):
    """Отправка, упершаяся в ограничение, откликом не считается.

    Письма нет; зачесть его значило бы навсегда закрыть вакансию от
    следующей попытки.
    """
    outbox.error = FloodWait(value=42)
    bot, hr, vacancy = await ready_to_send()

    assert await bot.send(hr, "письмо", vacancy_id=vacancy.id) is False

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NEW
    assert await all_rows(session_factory, Message) == []
    assert await all_rows(session_factory, VacancyEvent) == []


async def test_a_rate_limit_is_remembered_until_it_expires(
    ready_to_send, session_factory, outbox
):
    """Запрет запоминается со сроком, а не просто как «было».

    По нему автоматика молчит до конца окна: продолжив стучаться, она
    получила бы запрет подольше.
    """
    outbox.error = FloodWait(value=42)
    bot, hr, vacancy = await ready_to_send()
    before = time.time()

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    assert before + 42 <= bot.rs.flood_wait_until_ts <= time.time() + 42


async def test_a_successful_send_lifts_an_expired_rate_limit(
    ready_to_send, session_factory, outbox
):
    """Удачная отправка снимает запомненный запрет.

    Telegram отпустил; оставленный срок держал бы автоматику молча до
    своего конца без всякой причины.
    """
    bot, hr, vacancy = await ready_to_send()
    await bot.rs.set_app("flood_wait_until_ts", str(time.time() + 999))

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    assert bot.rs.flood_wait_until_ts == 0


async def test_a_suppressed_send_leaves_a_rate_limit_alone(ready_to_send, session_factory):
    """Заглушенная отправка запомненный запрет не трогает.

    Она до Telegram не доходила и о том, отпустил ли он, ничего не знает.
    """
    bot, hr, vacancy = await ready_to_send()
    await bot.rs.set_app("flood_wait_until_ts", "555")

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    assert bot.rs.flood_wait_until_ts == 555


async def test_a_letter_already_written_by_the_echo_is_not_a_mishap(
    ready_to_send, session_factory, outbox, caplog
):
    """Строка, положенная эхом раньше нас, бедой не считается.

    Своё письмо приходит к нам двумя дорогами — отсюда и эхом из Telegram, —
    и кто успел первым, заранее неизвестно. Повтор здесь штатный, а не сбой:
    строка одна, статус переведён, и жаловаться не на что. Ответь база
    отказом уникальности — в журнал ушла бы запись о сорвавшейся записи, и
    счётчик ошибок в окне зажёгся бы на ровном месте.
    """
    bot, hr, vacancy = await ready_to_send()
    await put(
        session_factory,
        message_row(
            hr_id=hr.id,
            is_incoming=False,
            tg_message_id=outbox.assigned_id,
            text="эхо успело раньше",
        ),
    )

    with caplog.at_level(logging.ERROR):
        assert await bot.send(hr, "письмо", vacancy_id=vacancy.id) is True

    assert len(await all_rows(session_factory, Message)) == 1
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
    # Отметка в ленте — единственный долговечный след того, что путь прошёл
    # до конца: журнал переживёт ротацию, а она остаётся.
    assert (await only_row(session_factory, VacancyEvent)).kind == "applied_sent"
    # Привязка к вакансии достаётся уцелевшей строке: эхо её не знает, а без
    # неё следующее обращение к тому же HR уйдёт полным письмом с резюме
    # вместо короткого догона, и ответ HR отнесётся не к той вакансии.
    assert (await only_row(session_factory, Message)).vacancy_id == vacancy.id


async def test_a_sent_letter_counts_even_when_the_record_failed(
    ready_to_send, session_factory, outbox
):
    """Ушедшее письмо засчитывается, даже если запись о нём не удалась.

    Сообщение у HR уже есть — отыграть назад нечего, и вернуть неудачу
    значило бы позвать вторую отправку тому же человеку.
    """
    bot, hr, vacancy = await ready_to_send()
    bot.session_factory = _BrokenCommits(session_factory, failures=1)

    assert await bot.send(hr, "письмо", vacancy_id=vacancy.id) is True


async def test_a_failed_record_still_moves_the_vacancy(
    ready_to_send, session_factory, outbox
):
    """Неудачная запись всё равно переводит вакансию в «отклик отправлен».

    Статус — единственное, что удержит повторную отправку: проверка
    «уже откликались» смотрит на него.
    """
    bot, hr, vacancy = await ready_to_send()
    bot.session_factory = _BrokenCommits(session_factory, failures=1)

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED
    assert await all_rows(session_factory, Message) == []


async def test_a_fallback_move_is_written_into_the_history(
    ready_to_send, session_factory, outbox
):
    """Запасной перевод статуса попадает в историю вакансии.

    Перевод тот же самый, что и при удачной записи, и в карточке он
    должен читаться так же. Без строки в истории статус выглядит
    сменившимся сам собой, и понять, кто и когда его тронул, нечем.
    Прочего следа у этого пути нет: ни строки письма, ни события
    «отклик отправлен» — их и потеряла сорвавшаяся запись.
    """
    bot, hr, vacancy = await ready_to_send()
    bot.session_factory = _BrokenCommits(session_factory, failures=1)

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    history = await only_row(session_factory, VacancyStatusHistory)
    assert history.previous_status is VacancyStatus.NEW
    assert history.status is VacancyStatus.APPLIED
    assert history.applied is True
    # Подпись — единственное, чем в карточке отличается сам собой ушедший
    # отклик от отправленного нажатием.
    assert history.explanation == "Авто-отправка отклика."


async def test_a_send_survives_a_failure_of_the_fallback_too(
    ready_to_send, session_factory, outbox
):
    """Отправка засчитывается, даже когда срывается и запасная запись.

    Защиты от повторной отправки не осталось вовсе, но письмо ушло —
    сказать «не отправлено» было бы прямой неправдой.
    """
    bot, hr, vacancy = await ready_to_send()
    bot.session_factory = _BrokenCommits(session_factory, failures=2)

    assert await bot.send(hr, "письмо", vacancy_id=vacancy.id) is True

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NEW
