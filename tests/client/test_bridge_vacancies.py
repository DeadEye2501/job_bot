"""Следствия слотов вакансий, которым хватает одной базы.

Предмет — то, что вакансия умеет сама по себе. Связывание с чужими карточками
лежит своим файлом, действия через бота — своим: там для ответа нужен кто-то
кроме базы.
"""

import json

from backend.models import VacancyStatus
from tests.dbio import put
from tests.factories import company_row, status_history_row, vacancy_row


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


async def test_notes_made_of_spaces_come_back_empty(api, ask, session_factory):
    """Заметка из одних пробелов возвращается пустой, а не пробелами.

    Окно принимает ответ за исходное состояние поля и сравнивает с ним
    набранное. Верни мост пробелы, которых в базе нет, — следующее же
    нажатие сочло бы поле изменённым и сохраняло бы его снова и снова.
    """
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(
        api.vacancies.save_notes, {"vacancy_id": vacancy.id, "notes": "   "}
    )

    assert answer["ok"]["notes"] is None


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
