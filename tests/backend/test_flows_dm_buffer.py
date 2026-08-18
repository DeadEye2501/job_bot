"""Следствия накопления входящих перед разбором ответа HR.

HR пишет очередью: «привет», «посмотрел резюме», «давайте созвонимся». Разбор
каждого по отдельности стоил бы трёх обращений к модели и трижды менял бы
статус вакансии по неполному тексту. Поэтому сообщения копятся, а таймер
взводится заново на каждом новом: разбор идёт, когда собеседник замолчал.

Накопитель ограничен сверху. Зациклившийся или спамящий собеседник иначе
раздул бы память, а пользы от тысячи строк нет: модель всё равно читает
только хвост.
"""

import asyncio

import pytest

from backend.payloads import PendingReply


def _texts(pipeline, hr_id):
    """Тексты, накопленные для собеседника."""
    return [item["text"] for item in pipeline.dm_classify_buffer.get(hr_id, [])]


async def test_a_message_waits_in_the_buffer_before_being_read(dm_pipeline):
    """Сообщение сперва ложится в накопитель, а не разбирается сразу."""
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "привет"))

    assert _texts(dm_pipeline, 7) == ["привет"]
    assert dm_pipeline.classified == []


async def test_a_burst_is_read_as_one_whole(dm_pipeline):
    """Очередь сообщений разбирается разом, а не по одному.

    Три обращения к модели вместо одного стоили бы втрое дороже и трижды
    двигали бы статус вакансии по неполному тексту.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 0
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "привет"))
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 11, 11, "посмотрел резюме"))
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 12, 12, "давайте созвонимся"))
    await asyncio.sleep(0.05)

    assert len(dm_pipeline.classified) == 1
    hr_id, batch = dm_pipeline.classified[0]
    assert hr_id == 7
    assert [item["text"] for item in batch] == [
        "привет",
        "посмотрел резюме",
        "давайте созвонимся",
    ]


async def test_a_new_message_pushes_the_reading_back(dm_pipeline):
    """Новое сообщение отодвигает разбор, а не запускает второй.

    Иначе собеседник, пишущий короткими строками, получал бы разбор после
    каждой — и статус вакансии прыгал бы по полуфразам.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 0.06
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "привет"))
    await asyncio.sleep(0.02)
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 11, 11, "и ещё"))
    await asyncio.sleep(0.03)

    assert dm_pipeline.classified == []

    await asyncio.sleep(0.06)

    assert len(dm_pipeline.classified) == 1
    assert [item["text"] for item in dm_pipeline.classified[0][1]] == ["привет", "и ещё"]


async def test_the_reading_waits_out_the_last_message_and_not_the_first(dm_pipeline):
    """Разбор идёт по сроку последнего сообщения, а не первого.

    Соседняя проверка ждёт дольше обоих сроков сразу и потому не различает,
    по чьему сроку разобрали. Здесь смотрят в тот единственный миг, когда
    срок первого сообщения уже вышел, а срок второго ещё нет: сторожится
    перевзвод отсчёта на каждом новом сообщении.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 0.3
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "привет"))
    await asyncio.sleep(0.2)
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 11, 11, "и ещё"))

    await asyncio.sleep(0.2)

    assert dm_pipeline.classified == []


async def test_two_correspondents_are_read_apart(dm_pipeline):
    """Два собеседника разбираются порознь: у каждого свой накопитель."""
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 0
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "от первого"))
    dm_pipeline.schedule_dm_classification(8, PendingReply(2, 20, 20, "от второго"))
    await asyncio.sleep(0.05)

    assert sorted(hr_id for hr_id, _ in dm_pipeline.classified) == [7, 8]


async def test_a_message_without_text_is_not_buffered(dm_pipeline):
    """Сообщение без текста в накопитель не идёт.

    Разбирать в картинке без подписи нечего, а само сообщение в базе уже
    лежит и в переписке видно.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, ""))

    assert 7 not in dm_pipeline.dm_classify_buffer
    assert 7 not in dm_pipeline.dm_classify_tasks


async def test_a_stopping_bot_buffers_nothing(dm_pipeline):
    """Останавливающийся бот новых сообщений не копит.

    Соединения к этому мигу уже закрываются, и отложенный разбор пошёл бы
    в закрытое.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.mark_shutting_down()
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "привет"))

    assert 7 not in dm_pipeline.dm_classify_buffer


async def test_an_overlong_burst_keeps_only_its_tail(dm_pipeline):
    """Слишком длинная очередь обрезается с начала, а не с конца.

    Свежий сигнал важнее полной истории: модель читает хвост, а
    зациклившийся собеседник иначе раздувал бы память без предела.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    cap = dm_pipeline.DM_CLASSIFY_BUFFER_CAP
    for number in range(cap + 3):
        dm_pipeline.schedule_dm_classification(
            7, PendingReply(1, number, number, f"строка {number}")
        )

    kept = _texts(dm_pipeline, 7)
    assert len(kept) == cap
    assert kept[0] == "строка 3"
    assert kept[-1] == f"строка {cap + 2}"


async def test_an_edited_message_is_updated_in_place(dm_pipeline):
    """Правка меняет текст в накопителе, не трогая порядок и соседей.

    Ищется письмо по номеру Telegram: оповещение о правке приходит оттуда и
    другого номера не знает. Номера здесь потому и разведены — с одним и тем
    же числом в обоих проверка прошла бы и при поиске по номеру строки базы,
    то есть не стерегла бы ничего: правка уходила бы в пустоту, а модель
    разбирала текст, которого HR уже не писал.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 500, 10, "первое"))
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 501, 11, "второе"))

    dm_pipeline.update_dm_buffer_text(7, 10, "первое, исправленное")

    assert _texts(dm_pipeline, 7) == ["первое, исправленное", "второе"]


async def test_an_edit_emptied_to_nothing_leaves_an_empty_string(dm_pipeline):
    """Правка в пустоту оставляет пустую строку, а не отсутствие.

    Дальше по пути тексты склеиваются переводом строки; отсутствие
    уронило бы склейку на первом же таком сообщении.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "первое"))

    dm_pipeline.update_dm_buffer_text(7, 10, None)

    assert _texts(dm_pipeline, 7) == [""]


@pytest.mark.parametrize(
    ("hr_id", "msg_id"),
    [
        pytest.param(8, 10, id="чужой собеседник"),
        pytest.param(7, 99, id="чужое сообщение"),
    ],
)
async def test_an_edit_of_something_not_buffered_changes_nothing(
    dm_pipeline, hr_id, msg_id
):
    """Правка того, чего в накопителе нет, ничего не меняет и не падает."""
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "первое"))

    dm_pipeline.update_dm_buffer_text(hr_id, msg_id, "мимо")

    assert _texts(dm_pipeline, 7) == ["первое"]


async def test_a_deleted_message_leaves_the_buffer(dm_pipeline):
    """Удалённое сообщение выбывает из накопителя, соседи остаются.

    Учитывать в решении то, что собеседник забрал назад, — прямой путь к
    неверному статусу вакансии.

    Номера разведены по той же причине, что и у правки: оповещение об
    удалении знает только номер Telegram. Уцелевший сосед в проверке не для
    красоты — он отличает «выбыло нужное» от «стёрлось всё разом».
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 500, 10, "первое"))
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 501, 11, "второе"))

    dm_pipeline.remove_dm_buffer_msg(7, 10)

    assert _texts(dm_pipeline, 7) == ["второе"]


async def test_removing_the_last_message_drops_the_buffer_itself(dm_pipeline):
    """Удаление последнего сообщения убирает и сам накопитель.

    Пустой накопитель дожил бы до слива и заставил бы обратиться к модели
    с пустым пакетом.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "единственное"))

    dm_pipeline.remove_dm_buffer_msg(7, 10)

    assert 7 not in dm_pipeline.dm_classify_buffer


@pytest.mark.parametrize(
    ("hr_id", "msg_id"),
    [
        pytest.param(8, 10, id="чужой собеседник"),
        pytest.param(7, 99, id="чужое сообщение"),
    ],
)
async def test_removing_something_not_buffered_changes_nothing(
    dm_pipeline, hr_id, msg_id
):
    """Удаление того, чего в накопителе нет, ничего не меняет и не падает."""
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "первое"))

    dm_pipeline.remove_dm_buffer_msg(hr_id, msg_id)

    assert _texts(dm_pipeline, 7) == ["первое"]
async def test_a_telegram_number_does_not_hit_a_row_number(dm_pipeline):
    """Совпадение номера Telegram с чужим номером строки чужого не трогает.

    Номера у письма два, и живут они в разных счётах: номер строки базы растёт
    сам по себе, номер Telegram — свой у каждой переписки. Совпасть они могут
    когда угодно, и раньше копилка искала по номеру строки, а звали её с
    номером Telegram: удаление одного письма выбрасывало соседнее, живое, а
    правка переписывала чужой текст. Модель после этого разбирала то, чего HR
    не писал, и двигала статус вакансии по чужому письму.

    Здесь у второго письма номер строки — 10, ровно тот номер Telegram, по
    которому уходит первое.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 500, 10, "первое"))
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 11, "второе"))

    dm_pipeline.remove_dm_buffer_msg(7, 10)

    assert _texts(dm_pipeline, 7) == ["второе"]

    dm_pipeline.update_dm_buffer_text(7, 11, "второе, переписанное")

    assert _texts(dm_pipeline, 7) == ["второе, переписанное"]
