"""Следствия отметки о разобранном и признака недоразобранной вакансии.

У каждого канала своя отметка: до какого сообщения бот дошёл. Со следующего
обхода он берёт только то, что новее, — иначе каждый обход перечитывал бы
канал с начала и тратил бы обращение к модели на каждое старое объявление.

Недоразобранная вакансия — та, у которой строка есть, а разбор не кончился:
процесс упал на середине, модель не ответила, пользователь закрыл окно.
Признак читается явным полем, а не по отсутствию названия: у отбракованной
вакансии названия тоже нет, но разобрана она полностью.
"""

from backend.flows import channels
from backend.models import TelegramChannel, VacancyStatus
from tests.dbio import only_row, put
from tests.factories import channel_row, vacancy_row


async def test_the_cursor_moves_to_the_message_just_handled(
    make_pipeline, session_factory
):
    """Отметка переезжает на разобранное сообщение.

    Со следующего обхода канал читается с этого места; без переезда
    каждый обход перечитывал бы его с начала.
    """
    await put(session_factory, channel_row(last_processed_msg_id=100))
    channel = await only_row(session_factory, TelegramChannel)
    pipeline = await make_pipeline()

    await channels._advance_cursor(pipeline, channel.id, 250)

    assert (await only_row(session_factory, TelegramChannel)).last_processed_msg_id == 250


async def test_the_first_pass_sets_the_cursor_from_scratch(
    make_pipeline, session_factory
):
    """У канала без отметки она заводится с первого же разбора."""
    await put(session_factory, channel_row(last_processed_msg_id=None))
    channel = await only_row(session_factory, TelegramChannel)
    pipeline = await make_pipeline()

    await channels._advance_cursor(pipeline, channel.id, 250)

    assert (await only_row(session_factory, TelegramChannel)).last_processed_msg_id == 250


async def test_a_cursor_for_a_missing_channel_is_not_created(
    make_pipeline, session_factory
):
    """Отметка по удалённому каналу не заводится и не падает.

    Канал могли удалить из окна прямо во время обхода.
    """
    pipeline = await make_pipeline()

    await channels._advance_cursor(pipeline, 404, 250)

    assert await only_row(session_factory, TelegramChannel) is None


async def test_an_unfinished_parse_is_recognised(make_pipeline, session_factory):
    """Вакансия с неоконченным разбором опознаётся как недоразобранная.

    Такие остаются после падения на середине: строка есть, вектор есть, а
    разбор не дошёл до конца.
    """
    await put(session_factory, vacancy_row(title=None, is_parsed=False))
    pipeline = await make_pipeline()

    assert await pipeline._is_unparsed_vacancy(1) is True


async def test_a_finished_parse_is_not_mistaken_for_unfinished(
    make_pipeline, session_factory
):
    """Разобранная вакансия недоразобранной не считается."""
    await put(session_factory, vacancy_row(title="разобрана", is_parsed=True))
    pipeline = await make_pipeline()

    assert await pipeline._is_unparsed_vacancy(1) is False


async def test_a_rejected_vacancy_without_a_title_is_still_parsed(
    make_pipeline, session_factory
):
    """Отбракованная вакансия без названия считается разобранной.

    Признак читается явным полем нарочно: у пустого объявления названия
    нет, но разбор по нему прошёл до конца и вынес отказ. Судя по
    названию, его гоняли бы через модель заново на каждом запуске.
    """
    await put(
        session_factory,
        vacancy_row(
            title=None,
            is_parsed=True,
            status=VacancyStatus.NOT_FIT,
            skip_reason="empty:нет текста",
        ),
    )
    pipeline = await make_pipeline()

    assert await pipeline._is_unparsed_vacancy(1) is False


async def test_a_vacancy_that_no_longer_exists_is_not_unfinished(make_pipeline):
    """Исчезнувшая вакансия недоразобранной не считается.

    Её могли удалить из окна, пока подбор недоразобранного шёл по
    списку; браться за неё уже не за что.
    """
    pipeline = await make_pipeline()

    assert await pipeline._is_unparsed_vacancy(404) is False
