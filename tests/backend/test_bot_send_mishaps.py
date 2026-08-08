"""Что остаётся после отправки, пошедшей не так.

Две беды разной природы. Telegram может отказать «слишком часто» — тогда
письма нет вовсе, и час запрета запоминается, чтобы автоматика не долбилась
в закрытую дверь. А может не удаться запись о письме, которое уже ушло, —
и вот это назад не отыграть: сообщение у HR есть.

Во втором случае статус переставляется отдельной короткой сделкой. Запись о
письме потеряна, зато повторная отправка отобьётся проверкой «уже
откликались» — второе письмо тому же HR хуже дырки в истории.
"""

import time

from pyrogram.errors import FloodWait

from backend.models import Message, Vacancy, VacancyEvent, VacancyStatus
from tests.dbio import all_rows, only_row


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

    assert before + 42 <= bot._rs.flood_wait_until_ts <= time.time() + 42


async def test_a_successful_send_lifts_an_expired_rate_limit(
    ready_to_send, session_factory, outbox
):
    """Удачная отправка снимает запомненный запрет.

    Telegram отпустил; оставленный срок держал бы автоматику молча до
    своего конца без всякой причины.
    """
    bot, hr, vacancy = await ready_to_send()
    await bot._rs.set_app("flood_wait_until_ts", str(time.time() + 999))

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    assert bot._rs.flood_wait_until_ts == 0


async def test_a_suppressed_send_leaves_a_rate_limit_alone(ready_to_send, session_factory):
    """Заглушенная отправка запомненный запрет не трогает.

    Она до Telegram не доходила и о том, отпустил ли он, ничего не знает.
    """
    bot, hr, vacancy = await ready_to_send()
    await bot._rs.set_app("flood_wait_until_ts", "555")

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    assert bot._rs.flood_wait_until_ts == 555


async def test_a_sent_letter_counts_even_when_the_record_failed(
    ready_to_send, session_factory, outbox
):
    """Ушедшее письмо засчитывается, даже если запись о нём не удалась.

    Сообщение у HR уже есть — отыграть назад нечего, и вернуть неудачу
    значило бы позвать вторую отправку тому же человеку.
    """
    bot, hr, vacancy = await ready_to_send()
    bot._session_factory = _BrokenCommits(session_factory, failures=1)

    assert await bot.send(hr, "письмо", vacancy_id=vacancy.id) is True


async def test_a_failed_record_still_moves_the_vacancy(
    ready_to_send, session_factory, outbox
):
    """Неудачная запись всё равно переводит вакансию в «отклик отправлен».

    Статус — единственное, что удержит повторную отправку: проверка
    «уже откликались» смотрит на него.
    """
    bot, hr, vacancy = await ready_to_send()
    bot._session_factory = _BrokenCommits(session_factory, failures=1)

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED
    assert await all_rows(session_factory, Message) == []


async def test_a_send_survives_a_failure_of_the_fallback_too(
    ready_to_send, session_factory, outbox
):
    """Отправка засчитывается, даже когда срывается и запасная запись.

    Защиты от повторной отправки не осталось вовсе, но письмо ушло —
    сказать «не отправлено» было бы прямой неправдой.
    """
    bot, hr, vacancy = await ready_to_send()
    bot._session_factory = _BrokenCommits(session_factory, failures=2)

    assert await bot.send(hr, "письмо", vacancy_id=vacancy.id) is True

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NEW
