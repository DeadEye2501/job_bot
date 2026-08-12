"""Следствия удаления вакансии конвейером.

Удаление идёт через общий путь репозитория нарочно: у вакансии есть история
статусов и лента событий, и простое удаление строки оставило бы их висеть
сиротами. Заодно вычёркивается вектор — иначе удалённая вакансия продолжала бы
объявлять новые посты своими повторами.

Мусор удаляется иначе: перед удалением остаётся отметка о том, что канал
прислал негодное. Без неё в статистике канала «прислал N мусора» посчитать
нечего — строка вакансии исчезает целиком.
"""

from backend.flows import cleanup
from backend.flows import embeddings
import pytest

from backend.models import (
    TelegramChannel,
    TrashEvent,
    Vacancy,
    VacancyEvent,
    VacancyStatusHistory,
)
from tests.dbio import all_rows, only_row, put
from tests.factories import (
    channel_row,
    status_history_row,
    vacancy_event_row,
    vacancy_row,
)


@pytest.fixture
async def with_a_vacancy(make_pipeline, session_factory):
    """Конвейер и вакансия с историей, лентой и вектором в кэше."""
    await put(session_factory, channel_row())
    channel = await only_row(session_factory, TelegramChannel)
    await put(
        session_factory,
        vacancy_row(
            title="лишняя",
            source_channel_id=channel.id,
            source_msg_id=42,
            embedding=[0.1, 0.2],
        ),
    )
    vacancy = await only_row(session_factory, Vacancy)
    await put(
        session_factory,
        status_history_row(vacancy.id),
        vacancy_event_row(vacancy.id),
    )
    pipeline = await make_pipeline()
    await embeddings.ensure_embedding_cache(pipeline)
    return pipeline, vacancy, channel


async def test_a_deleted_vacancy_takes_its_history_with_it(
    with_a_vacancy, session_factory
):
    """Удалённая вакансия уносит свою историю и ленту.

    Внешние ключи в этом подключении не стерегутся, и простое удаление
    строки оставило бы записи висеть в никуда.
    """
    pipeline, vacancy, _ = with_a_vacancy

    await cleanup.forget_vacancy(pipeline, vacancy.id)

    assert await all_rows(session_factory, Vacancy) == []
    assert await all_rows(session_factory, VacancyStatusHistory) == []
    assert await all_rows(session_factory, VacancyEvent) == []


async def test_a_deleted_vacancy_leaves_the_embedding_cache(with_a_vacancy):
    """Удалённая вакансия вычёркивается из кэша векторов.

    Оставшись, она объявляла бы новые посты своими повторами — и те
    молча пропадали бы, не дойдя до списка.
    """
    pipeline, vacancy, _ = with_a_vacancy

    await cleanup.forget_vacancy(pipeline, vacancy.id)

    assert pipeline._embedding_ids.tolist() == []


async def test_the_facade_says_the_vacancy_was_forgotten(with_a_vacancy):
    """Через фасад конвейера удаление доходит и отвечает «удалено».

    Фасадом зовёт бот, а бота — кнопка удаления в окне. Что уносится вместе
    со строкой, сторожат соседи выше; здесь наблюдается ответ, по которому
    окно решает, что показать человеку.
    """
    pipeline, vacancy, _ = with_a_vacancy

    assert await pipeline.forget_vacancy(vacancy.id) is True


async def test_the_facade_says_when_there_was_nothing_to_delete(with_a_vacancy):
    """Удаление несуществующей строки отвечает отказом, а не молчанием.

    Окно по этому ответу говорит «вакансия не найдена»: строку мог убрать
    другой экран или сам конвейер, пока карточка была открыта.
    """
    pipeline, _, _ = with_a_vacancy

    assert await pipeline.forget_vacancy(10_000) is False


async def test_the_window_hears_about_both_lists(with_a_vacancy):
    """Окно узнаёт и о списке вакансий, и о контактах.

    У HR и компании счётчик вакансий изменился, а он показан прямо в
    строке списка.
    """
    pipeline, vacancy, _ = with_a_vacancy
    heard: list[str] = []
    pipeline.on_contacts_changed = lambda: heard.append("контакты")
    pipeline.on_vacancies_changed = lambda: heard.append("вакансии")

    await cleanup.forget_vacancy(pipeline, vacancy.id)

    assert heard == ["контакты", "вакансии"]


async def test_trash_leaves_a_mark_before_it_goes(with_a_vacancy, session_factory):
    """Мусор оставляет отметку до того, как исчезнуть.

    Строка вакансии удаляется целиком, и без отметки в статистике
    канала «прислал N негодного» считать было бы нечего.
    """
    pipeline, vacancy, channel = with_a_vacancy

    await cleanup.delete_vacancy_as_trash(pipeline, vacancy.id, "не про работу")

    mark = await only_row(session_factory, TrashEvent)
    assert mark.source_channel_id == channel.id
    assert mark.source_msg_id == 42
    assert mark.reason == "не про работу"
    assert await all_rows(session_factory, Vacancy) == []


async def test_trash_also_leaves_the_embedding_cache(with_a_vacancy):
    """Удалённый мусор из кэша векторов тоже вычёркивается."""
    pipeline, vacancy, _ = with_a_vacancy

    await cleanup.delete_vacancy_as_trash(pipeline, vacancy.id, "не про работу")

    assert pipeline._embedding_ids.tolist() == []


async def test_a_mark_for_a_vanished_vacancy_names_no_channel(
    make_pipeline, session_factory
):
    """Отметка по уже исчезнувшей вакансии остаётся без канала.

    Так бывает, когда её успели удалить из окна: отметить нечего, но
    падать на этом незачем.
    """
    pipeline = await make_pipeline()

    await cleanup.delete_vacancy_as_trash(pipeline, 404, "не про работу")

    mark = await only_row(session_factory, TrashEvent)
    assert mark.source_channel_id is None
    assert mark.source_msg_id is None
