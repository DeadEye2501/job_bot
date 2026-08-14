"""Домен «система»: то, чем страница живёт на любом экране.

Режим бота и ручной сбор она отсюда правит, здоровье связи и счёт
непрочитанного — читает; журнал,
снос данных и просьба к рабочему столу приходят примесями из соседних файлов.
Разрез по файлам — это раскладка одного домена, а не задел под вторую
реализацию: страница видит один предмет, `api.system`.

Имя файла — по домену, а не по слову «состояние»: под тем именем сюда тянуло
складывать всё, что где-то хранится, а хранится оно в хозяйстве (`hub`).
"""

from __future__ import annotations

import asyncio

import time

from backend import health
from backend.models import BotMode
from backend.payloads import int_or_none
from backend.repository import hr_list, messages as messages_repo
from client.bridge.answer import Denied, denied, reply
from client.bridge.desktop import Desktop
from client.bridge.hub import Hub
from client.bridge.journal import Journal
from client.bridge.refusals import NO_BOT, RUN_REFUSALS
from client.bridge.wipe import Wipe


_MODEL_PROBE_INTERVAL_S = 60.0
"""Как часто лампочка спрашивает саму модель, а не только базу и Telegram.

Реже остальных нарочно. Вопрос к модели — это перечень имён плюс пробное
обращение, то есть настоящая, пусть и однословная, генерация: спрашивай его
каждые пять секунд, и модель уже никогда не выгрузится из памяти, а
неподнятый провайдер напишет в журнал двадцать четыре трассировки в минуту —
ровно на первом запуске, пока человек заполняет мастер.

Ответ между опросами берётся прошлый: лампочка показывает положение дел
минутной давности, и это честнее, чем греть модель ради секундной точности.
"""

_MODEL_PROBE_TIMEOUT_S = 10.0
"""Сколько лампочка ждёт поставщика.

Назначен, не измерен: у самого клиента срок втрое больше общего срока ответа
моста, и молчащий поставщик унёс бы с собой не лампочку, а весь ответ — вместе
с режимом и счётом непрочитанного. Десять секунд — заведомо больше, чем отвечает
поднятая модель, и заведомо меньше срока ответа.
"""

class System(Journal, Wipe, Desktop):
    """То, что страница показывает всегда, на каком бы экране ни стояла.

    Режим бота, ручной сбор, здоровье связи и счёт непрочитанного — здесь;
    журнал, снос всех данных и открытие ссылки — примесями рядом.

    Своих часов у домена нет вовсе: здоровье и непрочитанное он считает по
    вопросу, а спрашивает их страница своим чередом — она одна знает, открыт ли
    экран, на котором это видно.

    Всё, что случается само, — обход начался и кончился, прогресс подвинулся,
    в журнал легла запись, пришло письмо — приходит вестью в очередь: дом у
    такого один.
    """

    def __init__(self, hub: Hub) -> None:
        self._hub = hub
        # Отметка и прошлый ответ пробы моделей: спрашивают их чаще, чем стоит
        # спрашивать саму модель, — см. `_MODEL_PROBE_INTERVAL_S`.
        self._models_probed_at: float = float("-inf")
        self._models_answer: tuple[bool, bool] = (False, False)
        self._models_in_flight = False
        self._open_journal()

    def initial(self) -> dict:
        """Всё, что нижняя полоса показывает всегда, — одним ответом.

        Одним, а не тремя: полосу страница рисует целиком, и приди одно без
        другого — она стояла бы наполовину пустой до первого своего опроса,
        то есть секунды после открытия.
        """

        async def run() -> dict:
            return {
                "health": await self._health(),
                "unread": await self._unread(),
                "mode": (await self._hub.rs.get_mode()).value,
            }

        return reply(self._hub.runner, run())

    def set_mode(self, mode: str) -> dict:
        """Переключить режим бота: выключен, только переписка, полный вперёд.

        Незнакомое имя отбивается, назвав присланное: прими мост что попало —
        бот остался бы в прежнем режиме, а переключатель на экране показывал
        бы новый, и человек считал бы отправку включённой.

        Бота будим сразу: иначе новый режим начал бы действовать с ближайшим
        ударом его собственных часов, а человек уже переключил тумблер.
        """
        try:
            chosen = BotMode(mode)
        # Только `ValueError`: перечень отвечает им и на незнакомое слово, и на
        # не-строку. Широкий набор соседей ловил бы здесь то, чего не бывает.
        except ValueError:
            return denied(f"Неизвестный режим: {mode!r}")

        async def run() -> dict:
            await self._hub.rs.set_mode(chosen)
            if self._hub.bot is not None:
                self._hub.bot.kick()
            return {"mode": chosen.value}

        return reply(self._hub.runner, run())

    def run_now(self) -> dict:
        """Кнопка обновления: один обход каналов помимо режима.

        Занятый цикл объясняют словами: иначе человек жмёт кнопку, ничего не
        происходит, и он жмёт её снова — так и не узнав, что обход уже идёт.
        """

        async def run() -> dict:
            bot = self._hub.bot
            if bot is None:
                raise Denied(NO_BOT, action="run_now")
            status = await bot.force_poll_once()
            if status == "ok":
                return {"action": "run_now", "status": status}
            raise Denied(
                RUN_REFUSALS.get(status, "Не удалось прогнать."),
                action="run_now",
                status=status,
            )

        return reply(self._hub.runner, run())

    def stop_run(self) -> dict:
        """Кнопка остановки: отменить идущий обход.

        Отмена уезжает на мотор, а не зовётся прямо отсюда: обход живёт
        задачей в его цикле, и трогать её из чужого потока нельзя.
        """

        async def run() -> dict:
            bot = self._hub.bot
            if bot is None:
                raise Denied(NO_BOT, action="stop_run")
            bot.cancel_current_poll()
            return {"action": "stop_run"}

        return reply(self._hub.runner, run())

    def unread_chats(self) -> dict:
        """Люди, от которых есть непрочитанное, — для списка над полосой.

        Свежее непрочитанное первым: список открывают, чтобы ответить, а
        отвечают на последнее пришедшее.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows = await hr_list.list_hrs_with_unread(session)
            return {"chats": rows}

        return reply(self._hub.runner, run())

    def events(self, after) -> dict:
        """Что случилось само по себе после названного номера.

        Единственный зов, который может не ответить сразу: он ждёт появления
        нового или своего срока (`events.WAIT_SECONDS`). Ждать здесь дёшево —
        замерено слайсом А3: зовы моста разбираются каждый на своём потоке, и
        ждущий не занимает собой остальных.

        Номер приходит от страницы, а не хранится тут: страниц у окна бывает
        несколько за одну жизнь моста — перезагрузка заводит новую, — и своя
        отметка у моста означала бы, что вернувшаяся страница не досчитается
        того, что случилось без неё.
        """
        return reply(self._hub.runner, self._hub.events.take(_after(after)))

    def health(self) -> dict:
        """Живо ли то, на чём держится работа: база, Telegram, обе модели."""
        return reply(self._hub.runner, self._health())

    def unread(self) -> dict:
        """Сколько писем ждут ответа — счёт над списком переписок."""
        return reply(self._hub.runner, self._unread())

    async def _health(self) -> dict:
        """Спросить всё, из чего собрана лампочка.

        Сами вопросы задаёт `backend.health`; здесь только ритм: базу и
        Telegram спрашиваем каждый раз, модели — раз в минуту.

        Порядок значим: база спрашивается первой, пока вопрос молодой. Вопрос
        к моделям ждёт ответа поставщика до нескольких минут, и соединение с
        базой, открытое после него, пришлось бы на движок, который за это
        время могли и закрыть.
        """
        alive = {
            "db": await health.database_alive(self._hub.session_factory),
            "tg": health.telegram_alive(self._hub.bot),
        }
        chat, embed = await self._models_alive()
        return {**alive, "chat": chat, "embed": embed}

    async def _unread(self) -> dict:
        """Сколько входящих писем не прочитаны."""
        async with self._hub.session_factory() as session:
            return {"count": await messages_repo.count_unread_incoming(session)}

    async def _models_alive(self) -> tuple[bool, bool]:
        """Отвечают ли обе модели — с прошлым ответом между опросами.

        Свой срок у этого вопроса потому, что он дорог: см.
        `_MODEL_PROBE_INTERVAL_S`. База и Telegram спрашиваются каждый раз,
        модели — раз в минуту.

        Отметка ставится **до** опроса, а не после, и пока опрос в полёте,
        второго не заводится. Иначе срок держался бы только на быстром
        поставщике: медленный отвечает дольше, чем его успевают спросить
        заново, — LM Studio подгружает модель до трёх минут, — и каждый вопрос
        заводил бы новую пару настоящих генераций поверх незакончившихся.
        """
        now = time.monotonic()
        stale = now - self._models_probed_at >= _MODEL_PROBE_INTERVAL_S
        if self._models_in_flight or not stale:
            return self._models_answer
        self._models_probed_at = now
        self._models_in_flight = True
        try:
            self._models_answer = await asyncio.wait_for(
                self._ask_models(), _MODEL_PROBE_TIMEOUT_S
            )
        except TimeoutError:
            # Не дождались — лампочка гаснет, и это честный ответ: поставщик,
            # думающий дольше отведённого, для человека и есть недоступный.
            # Ждать дольше нельзя ни в коем случае: тот же ответ несёт режим и
            # счёт непрочитанного, а срок у него общий — молчащий поставщик
            # унёс бы с собой всю нижнюю полосу.
            self._models_answer = (False, False)
        finally:
            self._models_in_flight = False
        return self._models_answer

    async def _ask_models(self) -> tuple[bool, bool]:
        return (
            await health.model_alive(self._hub.rs.chat, "chat"),
            await health.model_alive(self._hub.rs.embed, "embed"),
        )


def _after(asked) -> int:
    """Номер, после которого страница хочет новое, приведённый к целому от нуля.

    Негодное и отрицательное читаются как ноль — «с самого начала»: страница
    присылает сюда то, что сама же получила прошлым ответом, и порча этого
    числа означает её собственную поломку, а не злой умысел. Отказ в ответ
    остановил бы её цикл совсем, а ноль всего лишь пришлёт уже виденное.

    Ноль здесь несущий, и потому отрицательное отсекается отдельно: кольцо
    считает потерянным всё, что старше названного номера, и на отрицательном
    объявляет потерю даже пустое. Ответ тогда приходит мгновенно, номер не
    двигается — и страница с мостом сходятся в плотную петлю без передышки.
    """
    return max(0, int_or_none(asked) or 0)
