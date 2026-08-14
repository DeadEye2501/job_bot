"""Следствия очереди живых событий: что узнаёт окно, спросившее «что нового».

Случившееся само по себе бэкенд рождает сам — обход начался и кончился,
прогресс подвинулся, пришло письмо, легла строка журнала. Раньше это доставлял
Qt сигналом из чужого потока; теперь окно спрашивает само, а запрос ждёт.
Проверяется здесь именно доставка: доедет ли случившееся до спросившего, не
потеряется ли случившееся до вопроса и отпустит ли запрос, когда отвечать уже
некому.

**Чего здесь нет:** различения «очередь закрыта» и «нового нет». Закрытая
отвечает тем же, чем пустая, и признака у неё пока не заводится — потребитель
ему придёт слайсом А4, вместе со своим циклом на странице.
"""

import asyncio
import threading

from client.bridge.events import Events


async def test_what_happened_in_another_thread_reaches_the_waiting_window():
    """Событие, рождённое в чужом потоке, будит ждущего и доезжает целиком.

    Девять сообщений из одиннадцати рождаются в потоке мотора, а спрашивает окно
    из своего. Не доехав, полоса прогресса замерла бы на месте до конца обхода.
    """
    events = Events()
    threading.Timer(0.01, events.add, ("progress", {"done": 3})).start()

    # Свой срок у запроса длинный, чужой короткий: наоборот тест остался бы
    # зелёным и при мёртвой побудке — дождался бы своего срока и нашёл событие
    # уже лежащим.
    answer = await asyncio.wait_for(events.take(after=0, timeout=30), timeout=3)

    assert [(one["kind"], one["payload"]) for one in answer["events"]] == [
        ("progress", {"done": 3})
    ]


async def test_what_happened_before_the_question_is_not_lost():
    """Случившееся до вопроса лежит и достаётся первым же запросом, без ожидания.

    Страница приходит позже бэкенда — при запуске и после каждой перезагрузки. У
    прежнего канала это и был провал: сигнал, испущенный до готовности окна,
    пропадал молча.
    """
    events = Events()
    events.add("ingestion_started")

    answer = await asyncio.wait_for(events.take(after=0, timeout=5), timeout=1)

    assert [one["kind"] for one in answer["events"]] == ["ingestion_started"]


async def test_a_burst_is_taken_in_one_armful_and_in_order():
    """Вспышка забирается пачкой и в том порядке, в каком случилась.

    Прогресс за обход шлёт десятки сообщений. По одному за запрос окно
    отставало бы тем сильнее, чем быстрее идёт работа.
    """
    events = Events()
    for step in range(3):
        events.add("progress", {"done": step})

    answer = await events.take(after=0, timeout=1)

    assert [one["payload"]["done"] for one in answer["events"]] == [0, 1, 2]


async def test_the_named_number_cuts_off_what_was_already_seen():
    """Названный номер отсекает виденное: второй запрос отдаёт только новое.

    Без отсечения окно перерисовывало бы всю ленту на каждый вопрос, и своя же
    первая пачка приезжала бы вечно.
    """
    events = Events()
    events.add("unread", {"count": 1})
    first = await events.take(after=0, timeout=1)
    seen = first["events"][-1]["n"]

    events.add("unread", {"count": 2})
    second = await events.take(after=seen, timeout=1)

    assert [one["payload"]["count"] for one in second["events"]] == [2]


async def test_a_question_about_nothing_comes_back_empty_instead_of_hanging():
    """Не дождавшись нового, запрос возвращается пустым, а не висит.

    Своего срока у канала нет: зависший вызов оставляет запись о себе навсегда,
    и через несколько часов тишины их накопится столько же, сколько было
    вопросов.
    """
    events = Events()

    answer = await asyncio.wait_for(events.take(after=0, timeout=0.05), timeout=2)

    assert answer["events"] == []


async def test_closing_the_window_lets_go_of_the_one_still_waiting():
    """Закрытие отпускает ждущего сразу, а не по истечении срока.

    Окно закрывают в произвольный миг, и почти всегда — под ждущим запросом.
    Дожидаться срока значит держать закрытие приложения на эти секунды.
    """
    events = Events()
    threading.Timer(0.01, events.close).start()

    answer = await asyncio.wait_for(events.take(after=0, timeout=30), timeout=3)

    assert answer["events"] == []


async def test_a_question_asked_after_the_window_is_gone_answers_at_once():
    """Спросивший после закрытия получает ответ сразу, а не через полный срок.

    Будить его будет уже некому: очередь закрыта, и событий в ней не появится.
    Без этой ветки последний вопрос догорал бы четверть минуты, держа на себе
    закрытие приложения.

    Красной фазы у этого сторожа не было — он дописан после кода по находке
    ревью, и доверие заслуживает итоговым проходом.
    """
    events = Events()
    events.close()

    answer = await asyncio.wait_for(events.take(after=0, timeout=30), timeout=1)

    assert answer["events"] == []


async def test_overflow_is_confessed_rather_than_passed_over_in_silence():
    """Выпавшее из кольца названо потерей, а не выдано за отсутствие событий.

    Кольцо не бесконечно, и переполнить его может страница, ушедшая на
    перезагрузку посреди обхода. Промолчав, мы отдали бы ей неполную картину,
    неотличимую от полной, — и экран остался бы врать до следующей правки руками.
    """
    events = Events(keep=2)
    for step in range(3):
        events.add("progress", {"done": step})

    answer = await events.take(after=0, timeout=1)

    assert answer["missed"] is True
    assert [one["payload"]["done"] for one in answer["events"]] == [1, 2]
