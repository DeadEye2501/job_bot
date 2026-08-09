"""Следствия привязки ответа HR к вакансии, о которой он пишет.

Путей два. Если HR ответил цитатой нашего письма, вакансия берётся из этого
письма. Если написал просто так — из самой свежей его вакансии на момент
сообщения.
"""

from backend.repository.hr_identify import find_latest_vacancy_id_for_hr, resolve_reply_target_vacancy
from tests.dbio import put
from tests.factories import at, hr_row, message_row, vacancy_row


async def test_an_hr_without_vacancies_has_nothing_to_attribute_to(
    session, session_factory
):
    """У HR без вакансий привязывать ответ не к чему."""
    hr = hr_row()
    await put(session_factory, hr)

    assert await find_latest_vacancy_id_for_hr(session, hr.id) is None


async def test_attribution_picks_the_freshest_vacancy_by_posting_date(
    session, session_factory
):
    """Ответ привязывается к самой свежей вакансии — по дате публикации.

    Дата публикации у второй строки отсутствует, и вместо неё идёт дата
    создания, которая позже. Совпадение с порядком по одному лишь созданию
    этим исключено.
    """
    hr = hr_row()
    await put(session_factory, hr)
    fresh = vacancy_row(hr_id=hr.id, created_at=at(10), posted_at=at(50))
    stale = vacancy_row(hr_id=hr.id, created_at=at(30), posted_at=None)
    await put(session_factory, fresh, stale)

    assert await find_latest_vacancy_id_for_hr(session, hr.id) == fresh.id


async def test_a_vacancy_without_a_posting_date_can_still_be_the_freshest(
    session, session_factory
):
    """Вакансия без даты публикации выигрывает по дате создания.

    Это вторая половина подстановки, и без неё первая ничего не доказывает:
    при сортировке по одной лишь дате публикации пустое значение и так
    уходит в хвост, поэтому прежний набор дал бы тот же ответ без всякой
    подстановки. Здесь пустое значение обязано выиграть — а уйдя в хвост,
    проиграет.
    """
    hr = hr_row()
    await put(session_factory, hr)
    published_long_ago = vacancy_row(hr_id=hr.id, created_at=at(10), posted_at=at(10))
    created_recently = vacancy_row(hr_id=hr.id, created_at=at(50), posted_at=None)
    await put(session_factory, published_long_ago, created_recently)

    assert await find_latest_vacancy_id_for_hr(session, hr.id) == created_recently.id


async def test_an_unparsed_vacancy_is_never_the_attribution_target(
    session, session_factory
):
    """Недоразобранная вакансия целью привязки не становится.

    Сообщение, пришедшее в окно разбора, иначе перевело бы статус ещё не
    готовой строки.
    """
    hr = hr_row()
    await put(session_factory, hr)
    ready = vacancy_row(hr_id=hr.id, created_at=at(10), is_parsed=True)
    half = vacancy_row(hr_id=hr.id, created_at=at(50), is_parsed=False)
    await put(session_factory, ready, half)

    assert await find_latest_vacancy_id_for_hr(session, hr.id) == ready.id


async def test_a_vacancy_appearing_after_the_message_is_not_its_target(
    session, session_factory
):
    """Вакансия, появившаяся позже сообщения, целью привязки не становится.

    Иначе старое сообщение из догоняющего разбора откатило бы статус
    только что добавленной вакансии.
    """
    hr = hr_row()
    await put(session_factory, hr)
    before = vacancy_row(hr_id=hr.id, created_at=at(10))
    after = vacancy_row(hr_id=hr.id, created_at=at(50))
    await put(session_factory, before, after)

    assert await find_latest_vacancy_id_for_hr(session, hr.id, as_of=at(30)) == before.id

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
