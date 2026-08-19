"""Следствия порядка выдачи в `list_vacancies`.

Шесть ключей сортировки и метка активности, которую они считают. Метка — не
колонка: это наибольшее из четырёх времён, и вычисляется она в самом запросе,
чтобы по ней можно было сортировать. Отбора здесь нет: набор в каждом тесте
такой, что отобрать нечего, и порядок остаётся единственным предметом.
"""

from backend.models import VacancyStatus
from tests.dbio import put
from tests.factories import (
    at,
    message_row,
    status_history_row,
    vacancy_event_row,
    vacancy_row,
)


async def test_a_letter_from_the_hr_lifts_the_vacancy_in_the_list(
    titles, session_factory
):
    """Письмо собеседника поднимает вакансию в списке, как и всякая жизнь.

    Метку считают двое — список прямо в запросе и окно для показанных строк, —
    и ради общности их счёт объявлен одним местом. Проверка второй дороги
    нужна затем, что общность эта только на бумаге, пока обе не спрошены.
    """
    quiet = vacancy_row(title="тихая", created_at=at(20))
    written_to = vacancy_row(title="написал HR", created_at=at(10))
    await put(session_factory, quiet, written_to)
    await put(
        session_factory,
        message_row(vacancy_id=written_to.id, is_incoming=True, sent_at=at(30)),
    )

    assert await titles(sort="newest") == ["написал HR", "тихая"]


async def test_newest_puts_the_latest_activity_first(titles, session_factory):
    """«Сначала новые» ставит первой вакансию с самой поздней активностью.

    Баллы и статусы заданы наперекор порядку по времени нарочно: без этого
    ответ совпал бы с ответом любого из пяти остальных ключей, и подмена
    ветки `newest` телом соседней осталась бы незамеченной. С такими
    значениями ожидаемый порядок даёт только `newest`.
    """
    await put(
        session_factory,
        vacancy_row(
            title="средняя", created_at=at(20), score=90, status=VacancyStatus.OFFER
        ),
        vacancy_row(
            title="поздняя", created_at=at(30), score=10, status=VacancyStatus.GHOSTING
        ),
        vacancy_row(
            title="ранняя", created_at=at(10), score=50, status=VacancyStatus.NEW
        ),
    )

    assert await titles(sort="newest") == ["поздняя", "средняя", "ранняя"]


async def test_oldest_reverses_that_order(titles, session_factory):
    """«Сначала старые» выдаёт тот же набор в обратном порядке."""
    await put(
        session_factory,
        vacancy_row(title="средняя", created_at=at(20)),
        vacancy_row(title="поздняя", created_at=at(30)),
        vacancy_row(title="ранняя", created_at=at(10)),
    )

    assert await titles(sort="oldest") == ["ранняя", "средняя", "поздняя"]


async def test_a_later_posted_at_outranks_an_earlier_created_at(
    titles, session_factory
):
    """Более поздняя дата публикации перевешивает более раннее создание."""
    await put(
        session_factory,
        vacancy_row(title="создана позже", created_at=at(20), posted_at=None),
        vacancy_row(title="опубликована позже", created_at=at(10), posted_at=at(30)),
    )

    assert await titles(sort="newest") == ["опубликована позже", "создана позже"]


async def test_a_later_event_lifts_the_vacancy_to_the_top(titles, session_factory):
    """Позднее событие обработки поднимает вакансию наверх."""
    quiet = vacancy_row(title="без событий", created_at=at(20))
    busy = vacancy_row(title="с поздним событием", created_at=at(10))
    await put(session_factory, quiet, busy)
    await put(session_factory, vacancy_event_row(busy.id, created_at=at(30)))

    assert await titles(sort="newest") == ["с поздним событием", "без событий"]


async def test_a_later_status_change_lifts_the_vacancy_to_the_top(
    titles, session_factory
):
    """Поздняя смена статуса поднимает вакансию наверх."""
    quiet = vacancy_row(title="без истории", created_at=at(20))
    moved = vacancy_row(title="с поздней сменой", created_at=at(10))
    await put(session_factory, quiet, moved)
    await put(session_factory, status_history_row(moved.id, changed_at=at(30)))

    assert await titles(sort="newest") == ["с поздней сменой", "без истории"]


async def test_only_the_latest_of_several_events_counts(titles, session_factory):
    """Из нескольких событий в счёт идёт самое позднее, а не последнее и не первое.

    Набор построен так, чтобы три правдоподобных ответа расходились. У
    вакансии с событиями они лежат поздним и ранним именно в этом порядке
    вставки: наибольшее из них — 60, последнее вставленное — 10, наименьшее
    — тоже 10. Соперница создана в 30. Наибольшее выводит вперёд вакансию с
    событиями, любой из двух других ответов — соперницу.
    """
    busy = vacancy_row(title="позднее событие есть", created_at=at(0))
    plain = vacancy_row(title="событий нет вовсе", created_at=at(30))
    await put(session_factory, busy, plain)
    await put(
        session_factory,
        vacancy_event_row(busy.id, created_at=at(60)),
        vacancy_event_row(busy.id, created_at=at(10)),
    )

    assert await titles(sort="newest") == [
        "позднее событие есть",
        "событий нет вовсе",
    ]


async def test_only_the_latest_of_several_status_changes_counts(
    titles, session_factory
):
    """Из нескольких смен статуса в счёт идёт самая поздняя.

    История статусов сводится своим запросом, отдельным от событий, и его
    наибольшее приходится закреплять отдельно: тест про события эту ветку не
    трогает вовсе. Набор построен так же — поздняя смена вставлена раньше
    ранней, поэтому наибольшее, наименьшее и последнее вставленное дают три
    разных ответа.
    """
    moved = vacancy_row(title="поздняя смена есть", created_at=at(0))
    still = vacancy_row(title="смен нет вовсе", created_at=at(30))
    await put(session_factory, moved, still)
    await put(
        session_factory,
        status_history_row(moved.id, changed_at=at(60)),
        status_history_row(moved.id, changed_at=at(10)),
    )

    assert await titles(sort="newest") == ["поздняя смена есть", "смен нет вовсе"]


async def test_identical_activity_is_broken_by_id_in_the_sort_direction(
    titles, session_factory
):
    """При одинаковой активности спор решает идентификатор, и по направлению сортировки.

    Метка активности у обеих строк одна и та же, так что без разрешителя
    порядок задавала бы база по своему усмотрению. «Сначала новые» ставит
    вперёд строку, заведённую последней, «сначала старые» — заведённую первой.
    """
    await put(
        session_factory,
        vacancy_row(title="заведена первой", created_at=at(10)),
        vacancy_row(title="заведена второй", created_at=at(10)),
    )

    assert await titles(sort="newest") == ["заведена второй", "заведена первой"]
    assert await titles(sort="oldest") == ["заведена первой", "заведена второй"]


async def test_score_desc_puts_the_highest_first_and_the_scoreless_last(
    titles, session_factory
):
    """«Балл по убыванию» ставит наибольший первым, а вакансию без балла — в хвост."""
    await put(
        session_factory,
        vacancy_row(title="средний балл", score=50),
        vacancy_row(title="без балла", score=None),
        vacancy_row(title="высокий балл", score=90),
    )

    assert await titles(sort="score_desc") == [
        "высокий балл",
        "средний балл",
        "без балла",
    ]


async def test_score_asc_puts_the_lowest_first_and_the_scoreless_still_last(
    titles, session_factory
):
    """«Балл по возрастанию» переворачивает порядок, но вакансию без балла оставляет в хвосте.

    Хвост у обоих направлений один: `nulls_last` не переворачивается вместе с
    направлением. Вакансия без балла — не «наименьшая», а «неизвестная», и
    показывать её первой при возрастании было бы неверно.
    """
    await put(
        session_factory,
        vacancy_row(title="средний балл", score=50),
        vacancy_row(title="без балла", score=None),
        vacancy_row(title="низкий балл", score=10),
    )

    assert await titles(sort="score_asc") == [
        "низкий балл",
        "средний балл",
        "без балла",
    ]


async def test_equal_scores_fall_back_to_the_latest_activity(titles, session_factory):
    """При равных баллах порядок решает активность, от поздней к ранней.

    Третья строка с высшим баллом и самой ранней активностью нужна, чтобы
    ответ принадлежал именно `score_desc`: на одной паре равнобалльных
    порядок совпал бы и с `newest`, и с обеими сортировками по статусу.
    """
    await put(
        session_factory,
        vacancy_row(title="тот же балл, раньше", score=50, created_at=at(10)),
        vacancy_row(title="тот же балл, позже", score=50, created_at=at(30)),
        vacancy_row(title="балл выше, активность старше", score=90, created_at=at(0)),
    )

    assert await titles(sort="score_desc") == [
        "балл выше, активность старше",
        "тот же балл, позже",
        "тот же балл, раньше",
    ]


async def test_status_active_first_leads_with_an_offer(titles, session_factory):
    """«Сначала активные» ведёт оффером и заканчивает пропавшим без вести."""
    await put(
        session_factory,
        vacancy_row(title="пропала", status=VacancyStatus.GHOSTING),
        vacancy_row(title="новая", status=VacancyStatus.NEW),
        vacancy_row(title="оффер", status=VacancyStatus.OFFER),
        vacancy_row(title="тестовое", status=VacancyStatus.TEST),
    )

    assert await titles(sort="status_active_first") == [
        "оффер",
        "тестовое",
        "новая",
        "пропала",
    ]


async def test_status_new_first_leads_with_a_new_one(titles, session_factory):
    """«Сначала новые по статусу» ведёт новой, а оффер уводит вниз."""
    await put(
        session_factory,
        vacancy_row(title="пропала", status=VacancyStatus.GHOSTING),
        vacancy_row(title="новая", status=VacancyStatus.NEW),
        vacancy_row(title="оффер", status=VacancyStatus.OFFER),
        vacancy_row(title="тестовое", status=VacancyStatus.TEST),
    )

    assert await titles(sort="status_new_first") == [
        "новая",
        "тестовое",
        "оффер",
        "пропала",
    ]


async def test_the_same_status_falls_back_to_the_latest_activity(
    titles, session_factory
):
    """Внутри одного статуса порядок решает активность, от поздней к ранней.

    Третья строка с более сильным статусом и самой ранней активностью нужна,
    чтобы ответ принадлежал именно `status_active_first`: на одной паре
    одностатусных порядок совпал бы и с `newest`, и с сортировками по баллу.
    """
    await put(
        session_factory,
        vacancy_row(title="новая, раньше", status=VacancyStatus.NEW, created_at=at(10)),
        vacancy_row(title="новая, позже", status=VacancyStatus.NEW, created_at=at(30)),
        vacancy_row(
            title="оффер, активность старше",
            status=VacancyStatus.OFFER,
            created_at=at(0),
        ),
    )

    assert await titles(sort="status_active_first") == [
        "оффер, активность старше",
        "новая, позже",
        "новая, раньше",
    ]
