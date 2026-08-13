"""Следствия смены статуса вакансии — руками и автоматически.

Пути два, и ведут они себя по-разному нарочно. Ручная смена с экрана графом
переходов не ограничена: пользователь вправе поставить любой статус, и
липкие вроде «отказ» его не держат. Автоматическая, от разбора ответа HR,
графу подчиняется и запрещённый переход не записывает вовсе.
"""

from backend.models import StatusHistorySource, VacancyStatus
from backend.payloads import Classification
from backend.repository.vacancies_card import get_vacancy_detail
from backend.repository.vacancies_life import apply_classification, change_vacancy_status, update_status_history_explanation
from tests.dbio import put
from tests.factories import message_row, vacancy_row


async def test_a_missing_vacancy_has_no_status_to_change(session, session_factory):
    """У несуществующей вакансии статус не меняется, и ответа-записи нет."""
    await put(session_factory, vacancy_row())

    assert await change_vacancy_status(session, 10_000, VacancyStatus.OFFER, None) is None


async def test_an_idle_click_writes_nothing(session, session_factory):
    """Тот же статус без комментария истории не оставляет.

    Кнопка «Применить» нажимается и вхолостую, когда пользователь ничего не
    выбрал заново. Без этой охраны лента набивалась бы записями «из новой в
    новую».
    """
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)

    assert await change_vacancy_status(session, vacancy.id, VacancyStatus.NEW, "  ") is None

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.history == []


async def test_the_same_status_with_a_comment_is_recorded_as_not_applied(
    session, session_factory
):
    """Комментарий без смены статуса записывается с отметкой «не применено».

    Отметка отличает «пользователь оставил заметку к текущему состоянию» от
    «пользователь перевёл вакансию» — на экране это разные строки ленты.

    Статус взят не умолчальный нарочно: на «новой» обе стороны записи совпали
    бы со значением, которое построитель ставит сам, и подстановка чего угодно
    вместо настоящего прежнего статуса прошла бы незамеченной.
    """
    vacancy = vacancy_row(status=VacancyStatus.IN_PROGRESS)
    await put(session_factory, vacancy)

    history = await change_vacancy_status(
        session, vacancy.id, VacancyStatus.IN_PROGRESS, "жду ответа"
    )

    assert history.applied is False
    assert history.status is VacancyStatus.IN_PROGRESS
    assert history.previous_status is VacancyStatus.IN_PROGRESS

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.status is VacancyStatus.IN_PROGRESS


async def test_a_real_change_moves_the_vacancy_and_is_recorded_as_applied(
    session, session_factory
):
    """Настоящая смена переводит вакансию и записывается с отметкой «применено»."""
    vacancy = vacancy_row(status=VacancyStatus.APPLIED)
    await put(session_factory, vacancy)

    history = await change_vacancy_status(
        session, vacancy.id, VacancyStatus.OFFER, "позвали"
    )

    assert history.applied is True
    assert history.previous_status is VacancyStatus.APPLIED
    assert history.status is VacancyStatus.OFFER
    assert history.source is StatusHistorySource.USER
    assert history.message_id is None

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.status is VacancyStatus.OFFER


async def test_a_manual_change_ignores_the_transition_graph(session, session_factory):
    """Ручная смена проходит и там, где автоматической ход закрыт.

    Из «отказа» граф авто-переходов не выпускает никуда. Пользователь всё
    равно должен мочь вернуть вакансию в работу — например, если отказ
    оказался недоразумением.
    """
    vacancy = vacancy_row(status=VacancyStatus.DECLINE)
    await put(session_factory, vacancy)

    history = await change_vacancy_status(
        session, vacancy.id, VacancyStatus.IN_PROGRESS, None
    )

    assert history.applied is True
    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.status is VacancyStatus.IN_PROGRESS


async def test_a_comment_gets_a_closing_period(session, session_factory):
    """Комментарию дописывается точка, если он не кончается знаком конца."""
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)

    history = await change_vacancy_status(
        session, vacancy.id, VacancyStatus.APPLIED, "  отправил отклик  "
    )

    assert history.explanation == "отправил отклик."


async def test_a_comment_already_closed_is_left_alone(session, session_factory):
    """Комментарий, уже кончающийся знаком конца, второй точки не получает."""
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)

    history = await change_vacancy_status(
        session, vacancy.id, VacancyStatus.APPLIED, "а зачем?"
    )

    assert history.explanation == "а зачем?"


async def test_an_explanation_of_a_missing_history_row_is_not_written(
    session, session_factory
):
    """Пояснение к несуществующей записи истории не пишется, и вызов об этом сообщает."""
    assert await update_status_history_explanation(session, 10_000, "текст") is None


async def test_an_explanation_can_be_replaced_and_cleared(session, session_factory):
    """Пояснение к записи истории заменяется, а пустое стирается в отсутствие."""
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)
    history = await change_vacancy_status(
        session, vacancy.id, VacancyStatus.APPLIED, "первая версия"
    )

    assert (await update_status_history_explanation(
        session, history.id, "вторая"
    )).explanation == "вторая."
    card = await get_vacancy_detail(session, vacancy.id)
    assert card.history[0].explanation == "вторая."

    assert (await update_status_history_explanation(
        session, history.id, "   "
    )).explanation is None
    card = await get_vacancy_detail(session, vacancy.id)
    assert card.history[0].explanation is None


async def test_an_automatic_verdict_on_a_missing_vacancy_changes_nothing(
    session, session_factory
):
    """Приговор классификатора о несуществующей вакансии ничего не пишет."""
    survivor = vacancy_row(status=VacancyStatus.APPLIED)
    await put(session_factory, survivor)

    await apply_classification(
        session, 10_000, 1, Classification(status=VacancyStatus.OFFER, explanation=None)
    )

    card = await get_vacancy_detail(session, survivor.id)
    assert card.vacancy.status is VacancyStatus.APPLIED
    assert card.history == []


async def test_an_allowed_automatic_verdict_moves_the_vacancy(
    session, session_factory
):
    """Разрешённый графом приговор переводит вакансию и ссылается на сообщение.

    Ссылка на сообщение — настоящая: внешние ключи в тестовой базе включены,
    и запись с выдуманным идентификатором она бы не приняла.
    """
    vacancy = vacancy_row(status=VacancyStatus.APPLIED)
    await put(session_factory, vacancy)
    reply = message_row(text="приглашаем", vacancy_id=vacancy.id)
    await put(session_factory, reply)

    await apply_classification(
        session,
        vacancy.id,
        reply.id,
        Classification(status=VacancyStatus.INVITATION, explanation="зовут на созвон"),
    )

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.status is VacancyStatus.INVITATION
    assert card.history[0].applied is True
    assert card.history[0].message_id == reply.id
    assert card.history[0].explanation == "зовут на созвон."


async def test_an_automatic_verdict_is_signed_by_the_system(session, session_factory):
    """Автоматический перевод подписан системой, а не человеком.

    Подписью строка от разбора ответа и отличается в ленте от строки, которую
    человек поставил с экрана: остальные колонки у них совпадают, и
    перепутанная подпись выдала бы приговор классификатора за решение
    пользователя.
    """
    vacancy = vacancy_row(status=VacancyStatus.APPLIED)
    await put(session_factory, vacancy)
    reply = message_row(text="приглашаем", vacancy_id=vacancy.id)
    await put(session_factory, reply)

    await apply_classification(
        session,
        vacancy.id,
        reply.id,
        Classification(status=VacancyStatus.INVITATION, explanation="зовут"),
    )

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.history[0].source is StatusHistorySource.SYSTEM


async def test_a_blocked_automatic_verdict_leaves_no_trace(session, session_factory):
    """Запрещённый графом приговор не пишет в ленту ничего.

    Раньше такой случай оставлял запись с отметкой «не применено», и она
    вылезала в ленте отдельной строкой, сбивая с толку. Входящее сообщение
    уже сохранено выше по стеку — следа достаточно.
    """
    vacancy = vacancy_row(status=VacancyStatus.DECLINE)
    await put(session_factory, vacancy)
    reply = message_row(text="приглашаем", vacancy_id=vacancy.id)
    await put(session_factory, reply)

    await apply_classification(
        session,
        vacancy.id,
        reply.id,
        Classification(status=VacancyStatus.INVITATION, explanation="зовут"),
    )

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.vacancy.status is VacancyStatus.DECLINE
    assert card.history == []


async def test_an_automatic_verdict_repeating_the_current_status_writes_nothing(
    session, session_factory
):
    """Приговор, повторяющий нынешний статус, тоже проходит мимо ленты."""
    vacancy = vacancy_row(status=VacancyStatus.APPLIED)
    await put(session_factory, vacancy)
    reply = message_row(text="без новостей", vacancy_id=vacancy.id)
    await put(session_factory, reply)

    await apply_classification(
        session,
        vacancy.id,
        reply.id,
        Classification(status=VacancyStatus.APPLIED, explanation="всё то же"),
    )

    card = await get_vacancy_detail(session, vacancy.id)
    assert card.history == []
