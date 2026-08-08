"""Следствия запуска в тестовом режиме.

Тестовый режим задаётся при сборке бота и означает одно: наружу не уходит
ничего. Отклик при этом считается сделанным — вакансия переходит в «отклик
отправлен», в ленте появляется отметка, — иначе прогнать сбор целиком, не
беспокоя живых HR, было бы нельзя.

Ручная отправка из вкладки «Контакты» ведёт себя иначе: там пользователь ждёт
именно письма, и молча его проглотить хуже, чем отказать словами.
"""

import pytest

from backend.models import Message, Vacancy, VacancyEvent, VacancyStatus
from tests.dbio import all_rows, only_row


async def test_a_cover_letter_is_not_sent_in_the_test_mode(ready_to_send, outbox):
    """В тестовом режиме письмо HR не уходит."""
    bot, hr, vacancy = await ready_to_send(dry_run=True)

    assert await bot.send(hr, "письмо", vacancy_id=vacancy.id) is True
    assert outbox.sent == []


async def test_a_suppressed_application_still_counts(
    ready_to_send, session_factory, outbox
):
    """Заглушенный отклик всё равно засчитывается.

    Иначе прогон сбора в тестовом режиме отправлял бы отклик по одной и
    той же вакансии на каждом обороте цикла.
    """
    bot, hr, vacancy = await ready_to_send(dry_run=True)

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED
    assert await all_rows(session_factory, Message) == []


async def test_the_timeline_marks_a_test_mode_send_as_suppressed(
    ready_to_send, session_factory, outbox
):
    """В ленте вакансии отправка помечена заглушенной.

    Сообщения в переписке нет ни при заглушке, ни при настоящей отправке;
    отличить одно от другого можно только по этой отметке.
    """
    bot, hr, vacancy = await ready_to_send(dry_run=True)

    await bot.send(hr, "письмо", vacancy_id=vacancy.id)

    assert (await only_row(session_factory, VacancyEvent)).payload["suppressed"] is True


async def test_a_chat_message_is_refused_with_the_reason_named(
    chatting, sending_unlocked
):
    """Сообщение из «Контактов» отклоняется с названной причиной.

    Пользователь ждёт именно письма; проглотить его молча значило бы
    показать отправленным то, чего HR не получит.
    """
    bot, client, hr = await chatting(dry_run=True)

    with pytest.raises(RuntimeError, match="тестовый режим"):
        await bot.send_to_hr_chat(hr.id, "здравствуйте")

    assert client.outgoing == []


async def test_a_file_is_refused_the_same_way(chatting, sending_unlocked, tmp_path):
    """Файл из «Контактов» отклоняется так же.

    Пути отправки два, и разойтись в поведении им нельзя: пользователь
    жмёт две соседние кнопки одного окна.
    """
    bot, client, hr = await chatting(dry_run=True)
    src = tmp_path / "снимок.png"
    src.write_bytes(b"\0")

    with pytest.raises(RuntimeError, match="тестовый режим"):
        await bot.send_to_hr_media(hr.id, str(src))

    assert client.outgoing == []
