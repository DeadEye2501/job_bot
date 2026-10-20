"""Вакансии по собственному адресу: есть ли в базе страница, которую завели снова."""

from backend.models import VacancyStatus
from backend.repository.vacancies_life import vacancies_at_address
from tests.dbio import put
from tests.factories import vacancy_row


async def test_the_same_page_written_otherwise_is_found(session_factory):
    """Строки без собственного адреса — вставленный текст, поля — поиску не мешают."""
    row = vacancy_row(source_url="https://hh.ru/vacancy/123")
    await put(session_factory, vacancy_row(), row)

    async with session_factory() as session:
        found = await vacancies_at_address(session, "http://spb.hh.ru/vacancy/123/?utm_source=tg")

    assert found == [row.id]


async def test_repeats_filed_earlier_come_by_number(session_factory):
    """Два повтора в базе — та же вакансия: оба, первая по номеру впереди."""
    first = vacancy_row(source_url="https://hh.ru/vacancy/123")
    second = vacancy_row(source_url="https://hh.ru/vacancy/123?from=main")
    await put(session_factory, first, second)

    async with session_factory() as session:
        assert await vacancies_at_address(session, "https://hh.ru/vacancy/123") == [first.id, second.id]


async def test_a_vacancy_is_found_in_any_status(session_factory):
    row = vacancy_row(source_url="https://hh.ru/vacancy/123", status=VacancyStatus.NOT_FIT)
    await put(session_factory, row)

    async with session_factory() as session:
        assert await vacancies_at_address(session, "https://hh.ru/vacancy/123") == [row.id]


async def test_a_link_in_the_text_is_not_the_vacancy_page(session_factory):
    """Сравниваются только собственные адреса: ссылка в тексте другой вакансии — упоминание."""
    await put(session_factory, vacancy_row(
        source_url="https://t.me/jobs_channel/15", source_msg_id=15, raw_text="Подробнее: https://hh.ru/vacancy/123",
    ))

    async with session_factory() as session:
        assert await vacancies_at_address(session, "https://hh.ru/vacancy/123") == []


async def test_a_post_is_found_by_its_link(session_factory):
    row = vacancy_row(source_url="https://t.me/pyjobs/5", source_msg_id=5)
    await put(session_factory, row)

    async with session_factory() as session:
        assert await vacancies_at_address(session, "https://t.me/s/pyjobs/5") == [row.id]


async def test_a_post_linked_from_fields_is_not_their_address(session_factory):
    """У набранной в «Полях» номера сообщения нет: ссылка на пост у неё —
    упоминание, в посте бывает несколько вакансий."""
    await put(session_factory, vacancy_row(source_url="https://t.me/pyjobs/5"))

    async with session_factory() as session:
        assert await vacancies_at_address(session, "https://t.me/pyjobs/5") == []


async def test_an_address_without_a_number_finds_nothing(session_factory):
    await put(session_factory, vacancy_row(source_url="https://acme.test/careers/python"))

    async with session_factory() as session:
        assert await vacancies_at_address(session, "https://acme.test/careers/python") == []
