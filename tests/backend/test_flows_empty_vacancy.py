"""Следствия сохранения объявления, из которого нечего было взять.

Такое объявление не выбрасывается, а помечается «не подходит» с причиной: в
окне оно видно, и пользователь сам решает, что с ним делать. Что модель всё же
вытащила — название, компанию, контакт — записывается: пустая карточка без
единой зацепки бесполезна.

Признак «разобрано» ставится и здесь. Разбор прошёл до конца и вынес отказ;
без признака подбор недоразобранного гонял бы это объявление через модель на
каждом запуске.

Когда модель не вытащила вообще ничего, прежние поля стираются. Иначе в
карточке рядом с причиной «пусто» висел бы прошлый разбор, и это выглядело бы
как ошибка приложения.
"""

from backend.flows import parse
import pytest

from backend.models import HR, Company, Vacancy, VacancyEvent, VacancyStatus
from tests.dbio import all_rows, only_row, put
from tests.factories import parsed_vacancy, vacancy_row
from tests.fakes.telegram import FakeTelegramClient, photo, user


@pytest.fixture
async def emptied(make_pipeline, session_factory):
    """Конвейер и вакансия с прошлым разбором в полях.

    Признак разбора снят нарочно: с ним «считается разобранной» было бы
    верно и до вызова, и проверка ничего бы не стерегла.
    """
    await put(
        session_factory,
        vacancy_row(
            title="прошлое название",
            description="прошлое описание",
            company_name="Прошлая",
            stack=["Python"],
            score=42,
            is_parsed=False,
        ),
    )
    vacancy = await only_row(session_factory, Vacancy)
    pipeline = await make_pipeline(FakeTelegramClient())
    return pipeline, vacancy


async def test_an_empty_vacancy_is_marked_unfit_with_a_reason(
    emptied, session_factory
):
    """Пустое объявление помечается «не подходит» с названной причиной.

    Оно остаётся видимым в окне: решать, что с ним делать, пользователю.
    """
    pipeline, vacancy = emptied

    await parse.save_empty_vacancy(pipeline, vacancy.id, parsed_vacancy(title="Хоть что-то"))

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "empty: no meaningful fields"
    assert saved.score == 0


async def test_an_empty_vacancy_counts_as_parsed(emptied, session_factory):
    """Пустое объявление считается разобранным.

    Разбор прошёл до конца и вынес отказ; без признака подбор
    недоразобранного гонял бы его через модель на каждом запуске.
    """
    pipeline, vacancy = emptied

    await parse.save_empty_vacancy(pipeline, vacancy.id, parsed_vacancy(title="Хоть что-то"))

    assert (await only_row(session_factory, Vacancy)).is_parsed is True


async def test_whatever_was_extracted_is_kept(emptied, session_factory):
    """Что модель всё же вытащила, то и записывается.

    Карточка без единой зацепки бесполезна: по названию пользователь
    хотя бы поймёт, о чём было объявление.
    """
    pipeline, vacancy = emptied

    await parse.save_empty_vacancy(pipeline, 
        vacancy.id,
        parsed_vacancy(title="Python-разработчик", location="Ереван"),
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.title == "Python-разработчик"
    assert saved.location == "Ереван"


async def test_nothing_extracted_wipes_the_previous_parse(emptied, session_factory):
    """Когда не вытащено ничего, прежний разбор стирается.

    Иначе в карточке рядом с причиной «пусто» висело бы прошлое
    название, и это читалось бы как поломка приложения.
    """
    pipeline, vacancy = emptied

    await parse.save_empty_vacancy(pipeline, vacancy.id, None)

    saved = await only_row(session_factory, Vacancy)
    assert saved.title is None
    assert saved.description is None
    assert saved.company_name is None
    assert saved.stack == []


async def test_the_company_is_linked_even_here(emptied, session_factory):
    """Компания привязывается и у непригодного объявления.

    Иначе в карточке имя компании есть, а перехода на неё нет — ссылка
    в окне ведёт в никуда.
    """
    pipeline, vacancy = emptied

    await parse.save_empty_vacancy(pipeline, 
        vacancy.id, parsed_vacancy(title="Что-то", company_name="Контур")
    )

    company = await only_row(session_factory, Company)
    assert (await only_row(session_factory, Vacancy)).company_id == company.id


async def test_the_hr_is_linked_even_here(session_factory, make_pipeline):
    """HR привязывается и у непригодного объявления.

    Тот же довод: переход на карточку HR из детали вакансии должен
    работать одинаково для любой вакансии.
    """
    client = FakeTelegramClient(
        users={"maria": user(id=777, username="maria", first_name="Мария")}
    )
    pipeline = await make_pipeline(client)
    await put(session_factory, vacancy_row(title="прошлое"))
    vacancy = await only_row(session_factory, Vacancy)

    await parse.save_empty_vacancy(pipeline, 
        vacancy.id, parsed_vacancy(title="Что-то", hr_contact="@maria")
    )

    hr = await only_row(session_factory, HR)
    assert (await only_row(session_factory, Vacancy)).hr_id == hr.id


async def test_an_hr_avatar_is_picked_up_on_the_way(session_factory, make_pipeline):
    """У найденного HR заодно забирается аватар.

    Второе обращение к Telegram ради картинки стоило бы отдельного
    ожидания, а собеседник уже под рукой.
    """
    client = FakeTelegramClient(
        users={
            "maria": user(
                id=777,
                username="maria",
                first_name="Мария",
                photo=photo(small_file_id="кар"),
            )
        },
        avatar=b"\x89PNG",
    )
    pipeline = await make_pipeline(client)
    await put(session_factory, vacancy_row(title="прошлое"))
    vacancy = await only_row(session_factory, Vacancy)

    await parse.save_empty_vacancy(pipeline, 
        vacancy.id, parsed_vacancy(title="Что-то", hr_contact="@maria")
    )

    assert (await only_row(session_factory, HR)).avatar == b"\x89PNG"


async def test_the_timeline_records_the_empty_parse(emptied, session_factory):
    """В ленте вакансии остаётся запись о разборе с нулевой оценкой.

    По ней видно, что бот объявление читал и решил именно так, а не
    пропустил его молча.
    """
    pipeline, vacancy = emptied

    await parse.save_empty_vacancy(pipeline, 
        vacancy.id, parsed_vacancy(title="Python-разработчик")
    )

    event = await only_row(session_factory, VacancyEvent)
    assert event.kind == "parsed"
    assert event.payload["score"] == 0
    assert event.payload["status"] == VacancyStatus.NOT_FIT.value
    assert event.payload["fields_filled"] == ["title"]
    assert event.payload["skip_reason"] == "empty: no meaningful fields"


async def test_the_timeline_says_nothing_was_filled(emptied, session_factory):
    """Когда не вытащено ничего, в ленте так и записано."""
    pipeline, vacancy = emptied

    await parse.save_empty_vacancy(pipeline, vacancy.id, None)

    saved = await only_row(session_factory, VacancyEvent)
    assert saved.payload["fields_filled"] == []


async def test_a_vanished_vacancy_is_left_alone(make_pipeline, session_factory):
    """По исчезнувшей вакансии ничего не записывается и не падает.

    Пользователь мог удалить её из окна, пока шёл разбор.
    """
    pipeline = await make_pipeline()

    await parse.save_empty_vacancy(pipeline, 404, parsed_vacancy(title="Что-то"))

    assert await all_rows(session_factory, VacancyEvent) == []


async def test_the_window_hears_about_both_lists(emptied):
    """Окно узнаёт и о вакансиях, и о контактах.

    У компании и HR счётчик вакансий изменился, а он показан прямо в
    строке списка.
    """
    pipeline, vacancy = emptied
    heard: list[str] = []
    pipeline.on_contacts_changed = lambda: heard.append("контакты")
    pipeline.on_vacancies_changed = lambda: heard.append("вакансии")

    await parse.save_empty_vacancy(pipeline, vacancy.id, parsed_vacancy(title="Что-то"))

    assert heard == ["контакты", "вакансии"]
