"""Следствия слотов вакансий, которым хватает одной базы.

Предмет — то, что вакансия умеет сама по себе. Связывание с чужими карточками
лежит своим файлом, действия через бота — своим: там для ответа нужен кто-то
кроме базы.
"""

import json

import pytest

from backend.models import VacancyStatus
from tests.dbio import put
from tests.factories import company_row, status_history_row, vacancy_row
from tests.factories_aggregators import (
    aggregator_row,
    application_row,
    screening_row,
    web_search_row,
)


async def test_the_filter_menus_come_by_their_own_ask(api, ask, session_factory):
    """Перечни для меню фильтра спрашивают своим зовом, а не вместе со списком.

    От поиска и страницы они не зависят вовсе: меню показывает все компании и
    все каналы, какие есть, иначе отбор сжимал бы их до того, что уцелело в
    выдаче. А список окно перечитывает на каждое нажатие клавиши в поиске — и
    приезжай перечни вместе с ним, каждый знак стоил бы лишнего полного прохода
    по таблице вакансий.
    """
    contour = company_row(name="Контур")
    await put(session_factory, contour)
    await put(
        session_factory,
        vacancy_row(title="Питонист", company_id=contour.id),
        vacancy_row(title="Не найдётся", company_name="Яндекс"),
    )

    answer = await ask(api.vacancies.filter_options)

    assert answer["ok"]["filter_options"]["companies"] == ["Контур", "Яндекс"]
    # И второе следствие: со списком они больше не едут. Верни их туда — и
    # каждый набранный в поиске знак снова стоил бы полного прохода по таблице,
    # а прогон остался бы зелёным.
    listed = await ask(api.vacancies.list)
    assert "filter_options" not in listed["ok"]


async def test_a_card_asked_by_a_broken_number_says_the_fields_are_wrong(api, ask):
    """Негодный номер карточки отбивают как негодное поле, а не как пропажу.

    Отказы эти разные: «вакансии нет» человек читает так, что строку снесли, и
    идёт перечитывать список; «неверные поля» значит, что сломалось окно. Уйди
    номер в запрос к базе как есть — оттуда вернулось бы первое.
    """
    answer = await ask(api.vacancies.detail, "не число")

    assert answer["fail"] == "fields"


async def test_the_list_carries_the_fields_the_pane_draws(
    api, ask, session_factory
):
    """Строка списка приезжает с тем, из чего окно её рисует.

    Список — единственное, что человек видит до первого нажатия: пропади в
    строке имя или отметка положения, и пустая полоса не скажет, какая это
    вакансия и что с ней уже сделали.
    """
    await put(
        session_factory, vacancy_row(title="Питонист", status=VacancyStatus.APPLIED)
    )

    answer = await ask(api.vacancies.list)

    row = answer["ok"]["vacancies"][0]
    assert row["title"] == "Питонист"
    assert row["status"] == "Applied"


async def test_the_parsed_salary_reaches_both_the_row_and_the_card(
    api, ask, session_factory
):
    """Разобранные числа зарплаты едут и в строку списка, и в карточку.

    Пилюлю зарплаты окно собирает само — из границ и единицы, а не из
    свободной строки объявления. Не доедь они, пилюля пропала бы у вакансии,
    сумма в которой разобрана и лежит в полях.
    """
    await put(
        session_factory,
        vacancy_row(salary_min=500000, salary_max=700000, salary_currency="֏"),
    )

    listed = await ask(api.vacancies.list)
    row = listed["ok"]["vacancies"][0]
    card = (await ask(api.vacancies.detail, row["id"]))["ok"]["vacancy"]

    assert (row["salary_min"], row["salary_max"], row["salary_currency"]) == (
        500000,
        700000,
        "֏",
    )
    assert (card["salary_min"], card["salary_max"], card["salary_currency"]) == (
        500000,
        700000,
        "֏",
    )


async def test_a_linked_company_name_beats_the_one_from_the_advert(
    api, ask, session_factory
):
    """Имя связанной компании побеждает написанное в объявлении.

    Связывают как раз затем, чтобы разнобой написаний в объявлениях свёлся к
    одному имени. Победи сырое — человек связал бы карточки и не увидел бы
    в списке никакой разницы.
    """
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(
        session_factory,
        vacancy_row(company_id=company.id, company_name="ООО «Рога»"),
    )

    answer = await ask(api.vacancies.list)

    row = answer["ok"]["vacancies"][0]
    assert row["company"] == "Контур"
    assert row["company_raw_name"] == "ООО «Рога»"


async def test_the_search_leaves_only_what_matches(api, ask, session_factory):
    """Поиск отбирает, а не подсвечивает: лишнее в окно не едет вовсе."""
    await put(
        session_factory, vacancy_row(title="Питонист"), vacancy_row(title="Дизайнер")
    )

    answer = await ask(api.vacancies.list, {"search": "Питон"})

    titles = [row["title"] for row in answer["ok"]["vacancies"]]
    assert titles == ["Питонист"]


async def test_a_page_says_whether_there_is_more_to_ask_for(
    api, ask, session_factory
):
    """Признак продолжения говорит окну, показывать ли догрузку.

    Без него окно либо просит следующую страницу вечно, либо не просит вовсе
    и прячет половину найденного.
    """
    await put(
        session_factory, vacancy_row(title="Первая"), vacancy_row(title="Вторая")
    )

    answer = await ask(api.vacancies.list, {"limit": 1, "offset": 0})

    assert len(answer["ok"]["vacancies"]) == 1
    assert answer["ok"]["has_more"] is True


async def test_a_filter_that_cannot_be_read_is_dropped_not_refused(
    api, ask, session_factory
):
    """Нечитаемое значение отбора выбрасывается, а список всё равно приходит.

    Отбор набирают на ходу, и полупустое поле — обычное состояние формы, а не
    ошибка. Ответь мост отказом — список гас бы на каждом втором нажатии.
    """
    await put(session_factory, vacancy_row())

    answer = await ask(api.vacancies.list, {"score_min": "не число"})

    assert len(answer["ok"]["vacancies"]) == 1


async def test_a_card_that_is_gone_is_named_as_gone(api, ask):
    """На пропавшую вакансию отвечают отказом с её номером.

    Карточку открывают из списка, а список к этому мигу мог устареть —
    вакансию удалили из другого окна. Без номера окно не поймёт, какую
    именно строку убирать с экрана.
    """
    answer = await ask(api.vacancies.detail, 404)

    assert answer["fail"] == "denied"
    assert answer["vacancy_id"] == 404


async def test_an_unknown_status_is_refused_by_name(api, ask, session_factory):
    """Незнакомое положение отбивается словами, а не поломкой.

    Названия положений живут и в окне, и в бэкенде; разойдись они — мост
    обязан сказать об этом внятно, иначе разбираться придётся по трассировке
    в журнале.
    """
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(
        api.vacancies.change_status,
        {"vacancy_id": vacancy.id, "status": "выдуманное"},
    )

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Неверный статус."


async def test_a_changed_status_reaches_the_card(api, ask, session_factory):
    """Смена положения доходит до карточки, а не только до ответа.

    Ответ об успехе окно принимает на веру и перерисовывает строку; если бы
    запись не доехала, следующее открытие карточки показало бы прежнее.
    """
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)

    saved = await ask(
        api.vacancies.change_status,
        {"vacancy_id": vacancy.id, "status": "Applied"},
    )
    assert "fail" not in saved

    shown = await ask(api.vacancies.detail, vacancy.id)
    assert shown["ok"]["vacancy"]["status"] == "Applied"


@pytest.mark.parametrize("act", ["change_status", "create", "delete"])
async def test_a_hand_edit_tells_the_window_the_list_changed(api, ask, hub, session_factory, act):
    """По этой вести значок «!» перечитывает число новых: без неё правка руками
    оставила бы на нём прежнее число, и нажатие брало бы не то, что обещано."""
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)
    payload = {
        "change_status": {"vacancy_id": vacancy.id, "status": "Not Fit"},
        "create": {"title": "Вакансия руками"},
        "delete": {"vacancy_id": vacancy.id},
    }[act]

    answer = await ask(getattr(api.vacancies, act), payload)

    assert "fail" not in answer
    news = await hub.events.take(0, timeout=0.1)
    assert "vacancies_list_changed" in [one["kind"] for one in news["events"]]


async def test_a_card_from_an_aggregator_names_its_source(api, ask, session_factory):
    """Пилюля источника у вакансии с агрегатора — как у вакансии из канала: имя
    источника приходит в карточке само, по привязке, без записи руками."""
    site = aggregator_row(name="Пример Работа", host="example.test")
    await put(session_factory, site)
    vacancy = vacancy_row(source_aggregator_id=site.id, source_key="vacancy/1",
                          source_url="https://example.test/vacancy/1")
    plain = vacancy_row()
    await put(session_factory, vacancy, plain)

    card = (await ask(api.vacancies.detail, vacancy.id))["ok"]["vacancy"]
    bare = (await ask(api.vacancies.detail, plain.id))["ok"]["vacancy"]

    assert (card["aggregator_name"], card["channel_username"]) == ("Пример Работа", None)
    assert card["from_web_search"] is False
    assert bare["aggregator_name"] is None


async def test_a_card_found_on_the_open_web_says_so(api, ask, session_factory):
    """У «Поиска по сети» имя — не источник, а способ поиска: окну нужно знать,
    что вакансия пришла с чужого сайта, а не с агрегатора."""
    web = web_search_row()
    await put(session_factory, web)
    vacancy = vacancy_row(source_aggregator_id=web.id, source_key="company.test/jobs/1",
                          source_url="https://company.test/jobs/1")
    await put(session_factory, vacancy)

    card = (await ask(api.vacancies.detail, vacancy.id))["ok"]["vacancy"]

    assert card["from_web_search"] is True


async def test_an_explanation_for_a_missing_record_is_refused(
    api, ask, session_factory
):
    """Объяснение к несуществующей записи истории не пишется молча.

    Записи истории окно держит у себя списком, и номер в нём мог устареть.
    Пройди правка тихо — человек считал бы, что объяснение сохранено.
    """
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(
        api.vacancies.save_history_explanation,
        {"vacancy_id": vacancy.id, "history_id": 999, "explanation": "почему"},
    )

    assert answer["fail"] == "denied"
    assert answer["history_id"] == 999


async def test_an_explanation_reaches_the_record(api, ask, session_factory):
    """Объяснение доходит до карточки, а не остаётся в ответе на сохранение.

    Им человек напоминает себе, почему вакансия оказалась в этом положении, и
    читает через недели, открыв карточку заново. Останься объяснение только в
    ответе — поле показалось бы пустым при следующем открытии.
    """
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    history = status_history_row(vacancy.id)
    await put(session_factory, history)

    saved = await ask(
        api.vacancies.save_history_explanation,
        {
            "vacancy_id": vacancy.id,
            "history_id": history.id,
            "explanation": "позвали на встречу",
        },
    )
    assert "fail" not in saved

    shown = await ask(api.vacancies.detail, vacancy.id)
    card = shown["ok"]["vacancy"]
    assert "позвали на встречу" in json.dumps(card, ensure_ascii=False)


async def test_a_deleted_vacancy_leaves_the_list(api, ask, session_factory):
    """Удалённая вакансия исчезает из списка, а не просто получает ответ.

    Бот в этом тесте не поднят, и удаление идёт прямым путём — той дорогой,
    которой пользуется окно, открытое до входа в Telegram.
    """
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(api.vacancies.delete, {"vacancy_id": vacancy.id})
    assert "ok" in answer
    assert answer["ok"]["action"] == "delete"

    listed = await ask(api.vacancies.list)
    assert listed["ok"]["vacancies"] == []


async def test_the_saved_note_comes_back_as_it_was_written_down(
    api, ask, session_factory
):
    """Окну возвращается то, что легло в колонку, а не то, что оно прислало.

    Заметку из одних пробелов база сводит к пустоте. Верни мост присланное —
    окно приняло бы пробелы за сохранённое и на следующем нажатии отправило
    бы их снова, затирая набранное человеком в это время.

    Прежняя заметка в строке стоит нарочно: на пустой колонке «вернули пустоту»
    и «вернули то, что лежит» неотличимы.
    """
    vacancy = vacancy_row(notes="было")
    await put(session_factory, vacancy)

    answer = await ask(
        api.vacancies.save_notes, {"vacancy_id": vacancy.id, "notes": "   "}
    )

    assert answer["ok"]["notes"] is None


async def test_the_saved_explanation_comes_back_with_its_period(
    api, ask, session_factory
):
    """Пояснение возвращается с точкой, которую дописала запись.

    Точку ставит репозиторий — в ленте событий строки идут вперемешку, и без
    неё соседние выглядели бы по-разному. Верни мост присланное без точки,
    и окно считало бы исходным то, чего в базе нет.
    """
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    history = status_history_row(vacancy_id=vacancy.id, explanation="старое")
    await put(session_factory, history)

    answer = await ask(
        api.vacancies.save_history_explanation,
        {
            "vacancy_id": vacancy.id,
            "history_id": history.id,
            "explanation": "передумал",
        },
    )

    assert answer["ok"]["explanation"] == "передумал."


async def test_a_card_says_whether_there_was_a_screening(api, ask, session_factory):
    """По признаку окно серит пункт «Скрининг». Письмо окно показывает первой
    репликой отклика, поэтому пункт открыт и по одному письму; отклик без письма
    и без реплик скрининга его не даёт."""
    screened, lettered, silent = vacancy_row(), vacancy_row(), vacancy_row()
    await put(session_factory, screened, lettered, silent)
    talked = application_row(screened.id)
    await put(session_factory, talked, application_row(lettered.id, letter="Письмо"),
              application_row(silent.id))
    await put(session_factory, screening_row(talked.id, 0))

    flags = [(await ask(api.vacancies.detail, one.id))["ok"]["vacancy"]["has_screening"]
             for one in (screened, lettered, silent)]

    assert flags == [True, True, False]


async def test_the_screening_comes_application_by_application(api, ask, session_factory):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    sent = application_row(vacancy.id, target="hr@company.test")
    await put(session_factory, sent)
    await put(session_factory, screening_row(sent.id, 0, text="Сколько лет опыта?"),
              screening_row(sent.id, 1, from_us=True, text="Пять"))

    answer = (await ask(api.vacancies.screening, vacancy.id))["ok"]

    assert answer == {"applications": [{
        "target": "hr@company.test",
        "lines": [{"from_us": False, "text": "Сколько лет опыта?"},
                  {"from_us": True, "text": "Пять"}],
    }]}


async def test_the_screening_of_a_missing_vacancy_is_refused(api, ask):
    answer = await ask(api.vacancies.screening, 999)

    assert (answer["fail"], answer["detail"]) == ("denied", "Вакансия не найдена")
