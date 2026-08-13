"""Следствия слотов вакансий, которым хватает одной базы.

Предмет — то, что вакансия умеет сама по себе. Связывание с чужими карточками
лежит своим файлом, действия через бота — своим: там для ответа нужен кто-то
кроме базы.
"""

import json

from backend.models import VacancyStatus
from tests.dbio import put
from tests.factories import company_row, status_history_row, vacancy_row


async def test_the_list_carries_the_fields_the_pane_draws(
    main_api, watch, session_factory
):
    """Строка списка приезжает с тем, из чего окно её рисует.

    Список — единственное, что человек видит до первого нажатия: пропади в
    строке имя или отметка положения, и пустая полоса не скажет, какая это
    вакансия и что с ней уже сделали.
    """
    caught = watch(main_api.vacancies_changed)
    await put(
        session_factory, vacancy_row(title="Питонист", status=VacancyStatus.APPLIED)
    )

    main_api.request_vacancies()

    row = (await caught.next())["vacancies"][0]
    assert row["title"] == "Питонист"
    assert row["status"] == "Applied"


async def test_a_linked_company_name_beats_the_one_from_the_advert(
    main_api, watch, session_factory
):
    """Имя связанной компании побеждает написанное в объявлении.

    Связывают как раз затем, чтобы разнобой написаний в объявлениях свёлся к
    одному имени. Победи сырое — человек связал бы карточки и не увидел бы
    в списке никакой разницы.
    """
    caught = watch(main_api.vacancies_changed)
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(
        session_factory,
        vacancy_row(company_id=company.id, company_name="ООО «Рога»"),
    )

    main_api.request_vacancies()

    row = (await caught.next())["vacancies"][0]
    assert row["company"] == "Контур"
    assert row["company_raw_name"] == "ООО «Рога»"


async def test_the_search_leaves_only_what_matches(main_api, watch, session_factory):
    """Поиск отбирает, а не подсвечивает: лишнее в окно не едет вовсе."""
    caught = watch(main_api.vacancies_changed)
    await put(
        session_factory, vacancy_row(title="Питонист"), vacancy_row(title="Дизайнер")
    )

    main_api.request_vacancies(json.dumps({"search": "Питон"}))

    titles = [row["title"] for row in (await caught.next())["vacancies"]]
    assert titles == ["Питонист"]


async def test_a_page_says_whether_there_is_more_to_ask_for(
    main_api, watch, session_factory
):
    """Признак продолжения говорит окну, показывать ли догрузку.

    Без него окно либо просит следующую страницу вечно, либо не просит вовсе
    и прячет половину найденного.
    """
    caught = watch(main_api.vacancies_changed)
    await put(
        session_factory, vacancy_row(title="Первая"), vacancy_row(title="Вторая")
    )

    main_api.request_vacancies(json.dumps({"limit": 1, "offset": 0}))

    answer = await caught.next()
    assert len(answer["vacancies"]) == 1
    assert answer["has_more"] is True


async def test_an_unknown_mode_comes_back_as_replace(main_api, watch, session_factory):
    """Незнакомый режим схлопывается в «заменить», а не едет обратно как есть.

    По этому слову окно решает, дописать ли пришедшее к показанному или
    заменить его. Верни ему опечатку — оно не поймёт, что делать со списком.
    """
    caught = watch(main_api.vacancies_changed)
    await put(session_factory, vacancy_row())

    main_api.request_vacancies(json.dumps({"mode": "как-нибудь"}))

    assert (await caught.next())["mode"] == "replace"


async def test_a_known_mode_comes_back_untouched(main_api, watch, session_factory):
    """Знакомый режим доезжает как есть — иначе догрузка не работала бы вовсе.

    Стоит рядом с проверкой опечатки нарочно: она одна была бы зелена и на
    мосте, который отвечает «заменить» всегда, — а такой мост стирал бы
    показанное на каждой подгрузке следующей страницы.
    """
    caught = watch(main_api.vacancies_changed)
    await put(session_factory, vacancy_row())

    main_api.request_vacancies(json.dumps({"mode": "append"}))

    assert (await caught.next())["mode"] == "append"


async def test_a_filter_that_cannot_be_read_is_dropped_not_refused(
    main_api, watch, session_factory
):
    """Нечитаемое значение отбора выбрасывается, а список всё равно приходит.

    Отбор набирают на ходу, и полупустое поле — обычное состояние формы, а не
    ошибка. Ответь мост отказом — список гас бы на каждом втором нажатии.
    """
    caught = watch(main_api.vacancies_changed)
    await put(session_factory, vacancy_row())

    main_api.request_vacancies(json.dumps({"score_min": "не число"}))

    assert len((await caught.next())["vacancies"]) == 1


async def test_a_card_that_is_gone_is_named_as_gone(main_api, watch):
    """На пропавшую вакансию отвечают отказом с её номером.

    Карточку открывают из списка, а список к этому мигу мог устареть —
    вакансию удалили из другого окна. Без номера окно не поймёт, какую
    именно строку убирать с экрана.
    """
    caught = watch(main_api.vacancy_detail_changed)

    main_api.request_vacancy_detail(404)

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["id"] == 404


async def test_notes_made_of_spaces_come_back_empty(main_api, watch, session_factory):
    """Заметка из одних пробелов возвращается пустой, а не пробелами.

    Окно принимает ответ за исходное состояние поля и сравнивает с ним
    набранное. Верни мост пробелы, которых в базе нет, — следующее же
    нажатие сочло бы поле изменённым и сохраняло бы его снова и снова.
    """
    caught = watch(main_api.vacancy_notes_saved)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.update_vacancy_notes(
        json.dumps({"vacancy_id": vacancy.id, "notes": "   "})
    )

    assert (await caught.next())["notes"] is None


async def test_an_unknown_status_is_refused_by_name(main_api, watch, session_factory):
    """Незнакомое положение отбивается словами, а не поломкой.

    Названия положений живут и в окне, и в бэкенде; разойдись они — мост
    обязан сказать об этом внятно, иначе разбираться придётся по трассировке
    в журнале.
    """
    caught = watch(main_api.vacancy_status_saved)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.change_vacancy_status(
        json.dumps({"vacancy_id": vacancy.id, "status": "выдуманное"})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Неверный статус."


async def test_a_changed_status_reaches_the_card(main_api, watch, session_factory):
    """Смена положения доходит до карточки, а не только до ответа.

    Ответ об успехе окно принимает на веру и перерисовывает строку; если бы
    запись не доехала, следующее открытие карточки показало бы прежнее.
    """
    saved = watch(main_api.vacancy_status_saved)
    shown = watch(main_api.vacancy_detail_changed)
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)

    main_api.change_vacancy_status(
        json.dumps({"vacancy_id": vacancy.id, "status": "Applied"})
    )
    assert (await saved.next())["ok"] is True

    main_api.request_vacancy_detail(vacancy.id)
    assert (await shown.next())["vacancy"]["status"] == "Applied"


async def test_an_explanation_for_a_missing_record_is_refused(
    main_api, watch, session_factory
):
    """Объяснение к несуществующей записи истории не пишется молча.

    Записи истории окно держит у себя списком, и номер в нём мог устареть.
    Пройди правка тихо — человек считал бы, что объяснение сохранено.
    """
    caught = watch(main_api.vacancy_history_explanation_saved)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.update_status_history_explanation(
        json.dumps(
            {"vacancy_id": vacancy.id, "history_id": 999, "explanation": "почему"}
        )
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["history_id"] == 999


async def test_an_explanation_reaches_the_record(main_api, watch, session_factory):
    """Объяснение доходит до карточки, а не остаётся в ответе на сохранение.

    Им человек напоминает себе, почему вакансия оказалась в этом положении, и
    читает через недели, открыв карточку заново. Останься объяснение только в
    ответе — поле показалось бы пустым при следующем открытии.
    """
    saved = watch(main_api.vacancy_history_explanation_saved)
    shown = watch(main_api.vacancy_detail_changed)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    history = status_history_row(vacancy.id)
    await put(session_factory, history)

    main_api.update_status_history_explanation(
        json.dumps(
            {
                "vacancy_id": vacancy.id,
                "history_id": history.id,
                "explanation": "позвали на встречу",
            }
        )
    )
    assert (await saved.next())["ok"] is True

    main_api.request_vacancy_detail(vacancy.id)
    card = (await shown.next())["vacancy"]
    assert "позвали на встречу" in json.dumps(card, ensure_ascii=False)


async def test_a_deleted_vacancy_leaves_the_list(main_api, watch, session_factory):
    """Удалённая вакансия исчезает из списка, а не просто получает ответ.

    Бот в этом тесте не поднят, и удаление идёт прямым путём — той дорогой,
    которой пользуется окно, открытое до входа в Telegram.
    """
    done = watch(main_api.vacancy_action_done)
    listed = watch(main_api.vacancies_changed)
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    main_api.delete_vacancy(json.dumps({"vacancy_id": vacancy.id}))
    answer = await done.next()
    assert answer["ok"] is True
    assert answer["action"] == "delete"

    main_api.request_vacancies()
    assert (await listed.next())["vacancies"] == []
