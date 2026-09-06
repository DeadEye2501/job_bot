"""Следствия привязки ответа HR к вакансии, о которой он пишет.

Путей два. Если HR ответил цитатой нашего письма, вакансия берётся из этого
письма. Если написал просто так — из последнего нашего письма ему.
"""

from backend.repository.hr_identify import find_last_outgoing_vacancy_id_for_hr
from backend.repository.hr_identify import resolve_reply_target_vacancy
from tests.dbio import put
from tests.factories import at, hr_row, message_row, vacancy_row


REPLIED_AT = at(90)
"""Когда пришёл ответ HR, к которому ищут вакансию.

Позже всех наших писем в наборах ниже: отсечка по времени — предмет
отдельной проверки, и в остальных мешать не должна.
"""


async def test_an_hr_we_never_wrote_to_has_nothing_to_attribute_to(
    session, session_factory
):
    """Пока мы этому HR не писали, привязывать ответ не к чему.

    Вакансия у него при этом есть: ленту его канала бот разбирает и без
    нашего отклика. Считай такую строку целью — ответ садился бы на
    вакансию, о которой мы не написали ни слова.
    """
    hr = hr_row()
    await put(session_factory, hr)
    await put(session_factory, vacancy_row(hr_id=hr.id))

    assert await find_last_outgoing_vacancy_id_for_hr(
        session, hr.id, as_of=REPLIED_AT
    ) is None


async def test_attribution_follows_our_letter_not_the_freshest_vacancy(
    session, session_factory
):
    """Ответ садится на вакансию нашего письма, а не на свежайшую у HR.

    Вакансия, разобранная после отклика, — обычное дело: тот же человек
    публикует следующую. Выбирай привязка свежайшую, ответ по вакансии, на
    которую мы откликались, уходил бы на соседнюю.
    """
    hr = hr_row()
    await put(session_factory, hr)
    written_about = vacancy_row(hr_id=hr.id, created_at=at(10))
    parsed_later = vacancy_row(hr_id=hr.id, created_at=at(50))
    await put(session_factory, written_about, parsed_later)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=written_about.id,
            is_incoming=False, sent_at=at(20),
        ),
    )

    assert await find_last_outgoing_vacancy_id_for_hr(
        session, hr.id, as_of=REPLIED_AT
    ) == written_about.id


async def test_the_latest_of_our_letters_is_the_target(session, session_factory):
    """Из наших писем целью становится последнее по времени отправки.

    Позднее письмо кладётся первым нарочно: догон заливает переписку
    задним числом, и у давнего письма номер строки выходит больше, чем у
    отправленного позже него. Совпади здесь порядок вставки с ожидаемым,
    отбор по номеру строки вместо времени прошёл бы молча.
    """
    hr = hr_row()
    await put(session_factory, hr)
    older = vacancy_row(hr_id=hr.id)
    newer = vacancy_row(hr_id=hr.id)
    await put(session_factory, older, newer)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=newer.id, is_incoming=False, sent_at=at(50)
        ),
        message_row(
            hr_id=hr.id, vacancy_id=older.id, is_incoming=False, sent_at=at(10)
        ),
    )

    assert await find_last_outgoing_vacancy_id_for_hr(
        session, hr.id, as_of=REPLIED_AT
    ) == newer.id


async def test_our_letter_to_another_hr_is_not_a_target(session, session_factory):
    """Письмо, написанное другому человеку, целью не становится.

    Собеседников у нас десятки, и пишем мы им вперемешку. Отвяжись отбор
    от своего человека — ответ садился бы на вакансию, о которой мы
    говорили с кем-то другим; беда вышла бы громче исходной, а заметить
    её было бы нечем.
    """
    ours = hr_row()
    stranger = hr_row()
    await put(session_factory, ours, stranger)
    mine = vacancy_row(hr_id=ours.id)
    theirs = vacancy_row(hr_id=stranger.id)
    await put(session_factory, mine, theirs)
    await put(
        session_factory,
        message_row(
            hr_id=ours.id, vacancy_id=mine.id, is_incoming=False, sent_at=at(10)
        ),
        message_row(
            hr_id=stranger.id, vacancy_id=theirs.id,
            is_incoming=False, sent_at=at(50),
        ),
    )

    assert await find_last_outgoing_vacancy_id_for_hr(
        session, ours.id, as_of=REPLIED_AT
    ) == mine.id


async def test_our_letter_without_a_vacancy_is_not_a_target(
    session, session_factory
):
    """Письмо, набранное руками в «Контактах», целью не становится.

    Номера вакансии у него нет, и привязка обязана дотянуться до письма
    постарше — иначе разговор о вакансии обрывался бы на первой же строке,
    написанной из окна переписки.
    """
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=hr.id)
    await put(session_factory, vacancy)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=vacancy.id, is_incoming=False, sent_at=at(10)
        ),
        message_row(
            hr_id=hr.id, vacancy_id=None, is_incoming=False, sent_at=at(50)
        ),
    )

    assert await find_last_outgoing_vacancy_id_for_hr(
        session, hr.id, as_of=REPLIED_AT
    ) == vacancy.id


async def test_a_letter_of_the_hr_is_not_a_target(session, session_factory):
    """Письмо самого HR целью не становится: считаются только наши.

    Номер вакансии у входящего письма стоит — его проставила эта самая
    привязка, когда письмо записывали. Считай мы такие строки, привязка
    читала бы собственный прошлый ответ вместо нашего письма и держалась
    бы за него, даже когда мы написали о другой вакансии.
    """
    hr = hr_row()
    await put(session_factory, hr)
    ours = vacancy_row(hr_id=hr.id)
    theirs = vacancy_row(hr_id=hr.id)
    await put(session_factory, ours, theirs)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=ours.id, is_incoming=False, sent_at=at(10)
        ),
        message_row(
            hr_id=hr.id, vacancy_id=theirs.id, is_incoming=True, sent_at=at(50)
        ),
    )

    assert await find_last_outgoing_vacancy_id_for_hr(
        session, hr.id, as_of=REPLIED_AT
    ) == ours.id


async def test_a_letter_sent_after_the_message_is_not_its_target(
    session, session_factory
):
    """Наше письмо, ушедшее позже ответа HR, целью для него не становится.

    Догон читает переписку задним числом, и старый ответ иначе садился бы
    на вакансию, о которой мы написали уже после него.
    """
    hr = hr_row()
    await put(session_factory, hr)
    before = vacancy_row(hr_id=hr.id)
    after = vacancy_row(hr_id=hr.id)
    await put(session_factory, before, after)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=before.id, is_incoming=False, sent_at=at(10)
        ),
        message_row(
            hr_id=hr.id, vacancy_id=after.id, is_incoming=False, sent_at=at(50)
        ),
    )

    assert await find_last_outgoing_vacancy_id_for_hr(
        session, hr.id, as_of=at(30)
    ) == before.id


async def test_a_reply_points_at_the_vacancy_of_the_letter_it_quotes(
    session, session_factory
):
    """Ответ на письмо привязывается к вакансии того самого письма.

    Проверяются обе цитаты, а не одна: с единственной проверкой отбор по
    номеру письма был бы не нужен вовсе — первая же строка HR подошла бы,
    и снятие этого условия прошло бы молча.
    """
    hr = hr_row()
    await put(session_factory, hr)
    about = vacancy_row(hr_id=hr.id, title="о чём письмо")
    other = vacancy_row(hr_id=hr.id, title="другая")
    await put(session_factory, about, other)
    await put(
        session_factory,
        message_row(hr_id=hr.id, vacancy_id=about.id, tg_message_id=41, is_incoming=False),
        message_row(hr_id=hr.id, vacancy_id=other.id, tg_message_id=42, is_incoming=False),
    )

    assert await resolve_reply_target_vacancy(session, hr.id, 41) == about.id
    assert await resolve_reply_target_vacancy(session, hr.id, 42) == other.id


async def test_a_quote_of_something_that_is_not_our_letter_points_nowhere(
    session, session_factory
):
    """Цитата не нашего письма ни к чему не привязывается."""
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=hr.id)
    await put(session_factory, vacancy)
    await put(
        session_factory,
        message_row(hr_id=hr.id, vacancy_id=vacancy.id, tg_message_id=41, is_incoming=True),
        message_row(hr_id=hr.id, vacancy_id=None, tg_message_id=42, is_incoming=False),
    )

    assert await resolve_reply_target_vacancy(session, hr.id, 41) is None
    assert await resolve_reply_target_vacancy(session, hr.id, 42) is None
    assert await resolve_reply_target_vacancy(session, hr.id, 99) is None
