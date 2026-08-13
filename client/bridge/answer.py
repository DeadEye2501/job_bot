"""Единый конверт ответа окну — от исхода работы до ответа зовущему.

Отправок здесь две, и это ненадолго: `reply` отдаёт ответ значением, как его
ждёт pywebview, а `_dispatch_json` — сигналом, как его ждал Qt. Вторая уходит
вместе с последним переехавшим доменом, слайсом А2.9.
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import CancelledError, Future
from typing import Any, Coroutine

from PySide6.QtCore import SignalInstance

from client.bridge.payload import _log_invalid_payload
from client.bridge.runner import AsyncRunner


logger = logging.getLogger(__name__)

# Срок назначен, а не выведен: он заведомо больше самой долгой работы, какую
# сегодня делает один метод, и заведомо меньше того времени, за которое человек
# решает, что окно повисло, и убивает его. Мерится в А3, где появляется окно.
REPLY_SECONDS = 60.0


def _ok(data: dict | None = None) -> str:
    return json.dumps({"ok": True, **(data or {})})


def _err(message: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": message, **extra})


class Denied(Exception):
    """Отказ, случившийся уже внутри работы: строки нет, имя занято.

    До мотора такое отвечается прямо, `denied`; изнутри работы отвечать нечем —
    возврат там занят исходом, — и отказ поднимается сюда броском. Ловит его
    `reply` и складывает тот же конверт.
    """

    def __init__(self, reason: str, **extra: Any) -> None:
        super().__init__(reason)
        self.reason = reason
        self.extra = extra


def denied(reason: str, **extra: Any) -> dict:
    """Отказ по делу: предмета нет, имя занято, поле пустое.

    Род один на все такие отказы, а различает их фраза: она и есть то, что
    человек прочтёт, и живёт она в `refusals`. Заводить род на каждую фразу
    незачем — окно показывает их одной плашкой и по роду не ветвится.
    """
    return {"fail": "denied", "detail": reason, **extra}


def bad_fields(where: str, error: Exception) -> dict:
    """Нагрузка не разобралась: жалоба в журнал без секретов, отказ окну.

    Три эти строки стояли своим телом в каждом слоте, читающем нагрузку, — на
    сорока восьми местах. Разъезжались они молча: чей-то слот забывал жалобу, и
    беда пропадала целиком.
    """
    _log_invalid_payload(where, error)
    return {"fail": "fields", "detail": f"Неверные поля: {error}"}


def reply(runner: AsyncRunner, coro: Coroutine[Any, Any, Any]) -> dict:
    """Сделать работу на моторе и вернуть её исход зовущему одним конвертом.

    Зовут отсюда из потока канала, а работа идёт на моторе, поэтому ждём мы
    здесь, а не там: pywebview отдаёт странице то, что вернул метод.

    Исход бывает четырёх родов, и все четыре — ответ. Молчания не бывает ни при
    каком: прежний канал на сорвавшейся работе просто не присылал сигнала, и
    окно оставалось со спиннером навсегда.

    **Отмена здесь отвечает, а рядом, в `_dispatch_json`, молчит** — и это не
    разнобой. Там ответ уезжал сигналом в страницу, которая при остановке уже
    отвалилась; здесь ответа ждёт зов, и промолчать значит держать его до срока
    впустую.

    Начатую работу срок не отменяет: `Future` от `run_coroutine_threadsafe`
    отзывает только то, что ещё не пошло. Отвечаем зовущему и оставляем работу
    доделываться — её исход просто некому будет прочесть.

    Звать это из потока самого мотора нельзя: работа, которой мы ждём, идёт в
    нём же, и ждать её значит запереть его на полный срок. Сегодня оттуда никто
    и не зовёт — там обратные вызовы бота, они кладут событие в очередь.
    """
    future = None
    try:
        future = runner.submit(coro)
        return {"ok": future.result(REPLY_SECONDS)}
    except Denied as e:
        return denied(e.reason, **e.extra)
    except (CancelledError, asyncio.CancelledError):
        return {"fail": "cancelled"}
    except Exception as e:
        if _our_deadline(e, future):
            return {"fail": "timeout"}
        logger.exception(
            "bridge: unexpected error in coroutine %s",
            getattr(coro, "__qualname__", "?"),
        )
        return {"fail": "broken", "detail": f"{type(e).__name__}: {e}"}


def _our_deadline(error: Exception, future: Future | None) -> bool:
    """Это наш срок вышел, а не работа сама не дождалась своего.

    Бьют они одним классом: внутренних сроков в мосте хватает — остановка бота,
    ожидание клиента. Различает их то, кончилась ли работа: наш срок застаёт её
    идущей, свой приходит вместе с её концом.
    """
    return isinstance(error, TimeoutError) and future is not None and not future.done()


def _dispatch_json(
    runner: AsyncRunner, signal: SignalInstance, coro: Coroutine[Any, Any, Any]
) -> None:
    """Отправить корутину на runner и отдать её ответ окну сигналом.

    Объявлено один раз на оба класса: общие чтения нагрузки зовут отправку,
    не зная, у какого из них они в руках, — а разойдись эти отправки, у
    мастера и настроек разошлось бы и поведение при закрытии окна.

    Отмену при остановке не показываем: обработчик в окне к этому мигу уже
    отвалился, и «CancelledError» уходило бы в умирающую страницу. Обе
    породы отмены ловятся вместе — runner отдаёт свою, корутина свою.
    """
    future = runner.submit(coro)

    def on_done(f: Future) -> None:
        try:
            payload = f.result()
        except (CancelledError, asyncio.CancelledError):
            return
        except Exception as e:
            logger.exception(
                "bridge: unexpected error in coroutine %s",
                getattr(coro, "__qualname__", "?"),
            )
            payload = _err(f"{type(e).__name__}: {e}")
        signal.emit(payload)

    future.add_done_callback(on_done)
