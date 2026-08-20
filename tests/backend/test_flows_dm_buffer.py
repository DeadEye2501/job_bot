"""Следствия накопления входящих перед разбором ответа HR.

HR пишет очередью: «привет», «посмотрел резюме», «давайте созвонимся». Разбор
каждого по отдельности стоил бы трёх обращений к модели и трижды менял бы
статус вакансии по неполному тексту. Поэтому сообщения копятся, а таймер
взводится заново на каждом новом: разбор идёт, когда собеседник замолчал.

Накопитель ограничен сверху. Зациклившийся или спамящий собеседник иначе
раздул бы память, а пользы от тысячи строк нет: модель всё равно читает
только хвост.
Проверяется здесь верхний слой: когда копить, когда разбирать и что доезжает до
копилки через переходники конвейера. Сама копилка — её пачки, предел и таймеры —
проверяется у себя (`test_flows_dm_debounce.py`): тяни оба слоя к одному
следствию, одна правка в копилке красила бы по два теста за раз.
"""

import asyncio
import logging

from backend.payloads import PendingReply


def _texts(pipeline, hr_id):
    """Тексты, накопленные для собеседника."""
    return [item["text"] for item in pipeline.dm_debounce.bursts.get(hr_id, [])]


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

    assert 7 not in dm_pipeline.dm_debounce.bursts
    assert 7 not in dm_pipeline.dm_debounce.timers


async def test_a_stopping_bot_buffers_nothing(dm_pipeline):
    """Останавливающийся бот новых сообщений не копит.

    Соединения к этому мигу уже закрываются, и отложенный разбор пошёл бы
    в закрытое.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.mark_shutting_down()
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "привет"))

    assert 7 not in dm_pipeline.dm_debounce.bursts


async def test_an_overflowed_burst_is_said_out_loud(dm_pipeline, caplog):
    """Обрезанная очередь не молчит: сколько выброшено, уходит в журнал.

    Сама обрезка — дело копилки, и там она и проверяется. Здесь другое
    следствие: имени человека копилка не знает и сказать о потере не может —
    говорит зовущий. Промолчи он, и модель разбирала бы хвост переписки
    вместо целого, а по журналу этого было бы не видно.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    cap = dm_pipeline.dm_debounce.cap

    with caplog.at_level(logging.WARNING):
        for number in range(cap + 2):
            dm_pipeline.schedule_dm_classification(
                7, PendingReply(1, number, number, f"строка {number}")
            )

    assert "dropping oldest" in caplog.text


async def test_an_edit_emptied_to_nothing_leaves_an_empty_string(dm_pipeline):
    """Правка в пустоту оставляет пустую строку, а не отсутствие.

    Дальше по пути тексты склеиваются переводом строки; отсутствие
    уронило бы склейку на первом же таком сообщении.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 30
    dm_pipeline.schedule_dm_classification(7, PendingReply(1, 10, 10, "первое"))

    dm_pipeline.update_dm_buffer_text(7, 10, None)

    assert _texts(dm_pipeline, 7) == [""]