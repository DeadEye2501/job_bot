"""Копилка отложенного разбора: пачки писем, таймеры над ними и начавшие."""

import asyncio


class DmDebounce:
    """Всё, чем живёт отложенный разбор переписки, — одной вещью.

    Четыре части держат общий договор, и порознь он не держится: пачка писем
    принадлежит человеку, таймер над ней — тому же человеку, а дотикав, таймер
    забирает пачку себе и переходит в начавшие. С этого мига отменять его
    нельзя: пачки в копилке уже нет, и отмена потеряла бы её насовсем. Пятое —
    разрешение обратиться к модели; сколько их дают разом, решено там, где это
    число ставят.

    Работы здесь нет: ни отсчёта срока, ни обращения к модели. Кто и когда
    правит копилку, решает `flows/dm_classify.py`.
    """

    def __init__(self, cap: int, slots: int) -> None:
        self.cap = cap
        self.bursts: dict[int, list[dict]] = {}
        self.timers: dict[int, asyncio.Task] = {}
        self.running: set[asyncio.Task] = set()
        self.slots = asyncio.Semaphore(slots)

    def remember(self, hr_id: int, letter: dict) -> int:
        """Записать письмо в пачку; сказать, сколько старых пришлось выбросить.

        Предел нужен от зациклившегося собеседника: пачка идёт в модель одним
        текстом, и та всё равно читает последние четыре тысячи знаков — свежее
        здесь дороже полного. Число выброшенных уходит наверх: имени человека
        тут нет, а запись в журнал без него бесполезна.
        """
        burst = self.bursts.setdefault(hr_id, [])
        burst.append(letter)
        if len(burst) <= self.cap:
            return 0
        dropped = len(burst) - self.cap
        del burst[:dropped]
        return dropped

    def retext(self, hr_id: int, tg_msg_id: int, text: str) -> None:
        """Переписать текст письма, ещё ждущего разбора.

        Письмо ищется по номеру Telegram: оповещение о правке приходит оттуда
        и другого номера не знает. Номер строки базы лежит в пачке рядом и
        служит другому — записи вердикта.
        """
        for letter in self.bursts.get(hr_id, []):
            if letter["tg_msg_id"] == tg_msg_id:
                letter["text"] = text
                return

    def forget(self, hr_id: int, tg_msg_id: int) -> None:
        """Выкинуть удалённое письмо из пачки; опустевшую пачку — тоже.

        Пустая пачка не безобидна: по ней числятся ожидающие разбора, и уход в
        OFF будил бы разбор ради ничего.
        """
        burst = self.bursts.get(hr_id)
        if not burst:
            return
        self.bursts[hr_id] = [
            letter for letter in burst if letter["tg_msg_id"] != tg_msg_id
        ]
        if not self.bursts[hr_id]:
            del self.bursts[hr_id]

    def take(self, hr_id: int) -> list[dict]:
        """Забрать пачку в разбор; второй раз её уже не отдадут."""
        return self.bursts.pop(hr_id, [])

    def restore(self, hr_id: int, burst: list[dict]) -> int:
        """Вернуть в копилку пачку, которую не удалось разобрать; сказать,
        сколько старых пришлось выбросить.

        Возвращают её, когда поставщик молчал: вердикта нет не потому, что
        письма нечем двигать, а потому, что спросить не вышло, — и потерять их
        значило бы потерять приглашение на созвон вместе с заминкой сети.

        Встают вернувшиеся перед накопившимся: они старше тех, что пришли, пока
        шло обращение к модели, а порядок в пачке несущий — решает последняя
        реплика. Предел тот же, что и при накоплении, и число выброшенных
        уходит наверх по той же причине: имени человека тут нет, а запись в
        журнал без него бесполезна.

        Правку и удаление, пришедшие из Telegram, пока пачка была на руках у
        разбора, возврат не знает: `retext` и `forget` правят то, что лежит в
        копилке, а вынутого там нет. Окно узкое — только неудавшийся зов, — и
        цена ему вердикт по отозванному письму; заводить ради этого учёт
        писем, ушедших в разбор, дороже самой беды.
        """
        if not burst:
            return 0
        together = burst + self.bursts.get(hr_id, [])
        dropped = max(0, len(together) - self.cap)
        del together[:dropped]
        self.bursts[hr_id] = together
        return dropped

    def drop(self, hr_id: int) -> None:
        """Бросить пачку неразобранной — так уходит написанное из чёрного."""
        self.bursts.pop(hr_id, None)

    def waiting(self) -> list[int]:
        """Люди, чьи пачки ждут разбора."""
        return [hr_id for hr_id, burst in self.bursts.items() if burst]

    def arm(self, hr_id: int, timer: asyncio.Task) -> None:
        """Поставить таймер над пачкой, погасив прежний.

        Прежний гасится затем, что срок отсчитывается от последнего письма:
        доживи он до конца, разбор ушёл бы в модель, не дождавшись мысли,
        дописанной вторым сообщением.

        Свежий таймер зовущий заводит до этого зова, и порядок от этого не
        страдает: до своего первого `await` зовущий не отдаёт ход, а значит
        новый таймер не тикнет ни разу, пока прежний не погашен.
        """
        prev = self.timers.get(hr_id)
        if prev is not None and not prev.done():
            prev.cancel()
        self.timers[hr_id] = timer

    def claim(self, hr_id: int, timer: asyncio.Task) -> bool:
        """Дотикавшему таймеру — добро на разбор, если он всё ещё свой.

        Отмена — просьба, а не приказ: погашенный таймер мог проснуться и
        дойти сюда, когда над человеком стоит уже другой. Разбери он пачку —
        вынул бы её из-под свежего таймера, и тот разобрал бы пустоту.
        """
        if self.timers.get(hr_id) is not timer:
            return False
        del self.timers[hr_id]
        return True

    def begin(self, reading: asyncio.Task) -> None:
        """Отметить разбор начавшимся: отменять его больше нельзя."""
        self.running.add(reading)

    def end(self, reading: asyncio.Task) -> None:
        """Отметить разбор конченым."""
        self.running.discard(reading)

    def busy(self) -> list[asyncio.Task]:
        """Разборы, идущие прямо сейчас, — их дожидаются, а не гасят."""
        return [task for task in self.running if not task.done()]

    def cancel_timers(self) -> list[asyncio.Task]:
        """Погасить спящие таймеры и отдать их — остановке нужно дождаться.

        Отдаются те, что гасили: дошедший до конца таймер ждать нечего, а
        погашенный ещё сидит на своём `await` и уйдёт не в этот миг.
        """
        timers = [task for task in self.timers.values() if not task.done()]
        for task in timers:
            task.cancel()
        return timers

    def forget_timers(self) -> None:
        """Забыть таймеры: остановка их уже погасила и дождалась."""
        self.timers.clear()

    def forget_bursts(self) -> None:
        """Забыть пачки: разбирать их некому — бот встал."""
        self.bursts.clear()
