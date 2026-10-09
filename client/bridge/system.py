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

import logging
import time
from concurrent.futures import Future

from backend import health
from backend.models import BotMode
from backend.repository.bot_mode import read_mode, write_mode
from backend.incoming import int_or_none
from backend.repository import hr_list, messages as messages_repo
from client.bridge.answer import Denied, denied, launched, reply
from client.bridge.desktop import Desktop
from client.bridge.hub import Hub
from client.bridge.journal import Journal
from client.bridge.refusals import NO_BOT, RUN_REFUSALS
from client.bridge.wipe import Wipe
from client.bridge.wire import _iso


logger = logging.getLogger(__name__)


_MODEL_PROBE_INTERVAL_S = 60.0
"""Как часто лампочка спрашивает поставщика, а не только базу и Telegram.

Разрежение осталось от времён, когда вопрос был дорогим — настоящей
генерацией. Сейчас он дёшев: перечень имён и ничего больше
(`health.model_alive`), и на живом поставщике это тысячные доли секунды.

Оставлено потому, что ответ на него всё равно меняется редко: имя модели
правят руками в настройках, поставщика поднимают и гасят не каждую минуту.
Двадцать четыре обращения в минуту на двоих ради ответа, который час не
меняется, — плата ни за что; лампочка показывает положение дел минутной
давности, и для «числится ли модель» этого довольно.

От наложения проб держат оба: срок и заслон `_models_in_flight`. Заслон
надёжнее — он работает при любом ритме часов.
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
                "mode": (await self._mode()).value,
            }

        return reply(self._hub.runner, run())

    async def _mode(self) -> BotMode:
        """Режим, записанный в базе. Читается на каждый показ, а не из кэша:
        переключить его могло и окно, и очередной удар часов бота."""
        async with self._hub.session_factory() as session:
            return await read_mode(session)

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
            async with self._hub.session_factory() as session:
                async with session.begin():
                    await write_mode(session, chosen)
            if self._hub.bot is not None:
                # Обход агента — отдельная задача и тика не ждёт: Off гасит его сразу.
                if chosen is BotMode.OFF:
                    self._hub.bot.cancel_round()
                self._hub.bot.kick()
            return {"mode": chosen.value}

        return reply(self._hub.runner, run())

    def human_done(self) -> dict:
        """«Готово» — человек прошёл капчу или вошёл на сайт, агент продолжает."""
        if self._hub.bot is not None:
            self._hub.bot.human_done()
        return {"ok": {}}

    def run_now(self) -> dict:
        """Кнопка обновления: один обход каналов помимо режима.

        Ответ говорит только «пущено»: обход идёт по всем каналам и по всем их
        новым постам — это самая долгая работа в приложении, и ждать её значит
        держать зов вместе с окном. Чем кончилось, человек узнаёт вестью, а о
        ходе рассказывает нижняя полоса.
        """
        bot = self._hub.bot
        if bot is None:
            return denied(NO_BOT, action="run_now")

        return launched(
            self._hub,
            bot.force_poll_once,
            RUN_REFUSALS,
            "Каналы прогнаны.",
            action="run_now",
        )

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
            return {"chats": [{**row, "last_at": _iso(row["last_at"])} for row in rows]}

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
        того, что случилось без неё. Пустота вместо номера значит «с этого
        мига»: у только что открывшейся страницы номера ещё нет.
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

        Порядок значим: база спрашивается первой, пока вопрос молодой. Первая
        проба моделей ждёт до трёх минут на адресе, который глотает пакеты, и
        соединение с базой, открытое после неё, пришлось бы на движок, который
        за это время могли и закрыть. Все пробы после первой уходят в сторону
        и не ждутся вовсе — см. `_models_alive`.
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
        """Прошлый ответ моделей; новую пробу ждёт только первая.

        Дальше первой пробы ответ не ждут вовсе, и это главное здесь. Адрес,
        который глотает пакеты — задремавшая машина в сети, закрытый
        межсетевым экраном порт, — не отказывает, а молчит до срока в три
        минуты (`lm_studio.LLM_REQUEST_TIMEOUT_SEC`). Жди лампочка ответа —
        на эти три минуты встал бы весь удар часов, а бьют они раз в пять
        секунд.

        Первую ждём: до неё не известно ничего, а «не знаю» лампочка показать
        не умеет — только «жив» и «мёртв». Отдай мы «мёртв» не спросив, окно
        погасило бы бота на первом же ударе часов после запуска — за красную
        лампочку оно гасит бота.

        Отметка ставится **до** пробы, а не после, и пока проба в полёте,
        второй не заводится: на таком адресе каждый удар часов заводил бы
        новую пару ожиданий поверх незакончившихся — тридцать шесть штук за
        те же три минуты.
        """
        now = time.monotonic()
        if self._models_in_flight or now - self._models_probed_at < _MODEL_PROBE_INTERVAL_S:
            return self._models_answer
        never_asked = self._models_probed_at == float("-inf")
        self._models_probed_at = now
        self._models_in_flight = True
        if never_asked:
            await self._probe_models()
        else:
            self._hub.runner.submit(self._probe_models()).add_done_callback(_probed)
        return self._models_answer

    async def _probe_models(self) -> None:
        """Спросить модели и оставить ответ той лампочке, что спросит следующей."""
        try:
            self._models_answer = await self._ask_models()
        finally:
            self._models_in_flight = False

    async def _ask_models(self) -> tuple[bool, bool]:
        return (
            await health.model_alive(self._hub.rs.chat, "chat"),
            await health.model_alive(self._hub.rs.embed, "embed"),
        )


def _probed(task: Future) -> None:
    """Прочитать исход отложенной пробы моделей.

    Ответа у неё не ждёт никто — в том и смысл: лампочка не должна стоять в
    очереди к занятой модели. Но брошенный отсюда бросок не попадает никуда:
    ни в ответ, ни в журнал, — и лампочка держала бы прошлое «жив» до самого
    закрытия окна, а разбирать это было бы не по чему.

    Отмена — не беда: мотор гасят вместе с окном, и незаконченная проба гаснет
    с ним заодно.
    """
    if task.cancelled():
        return
    trouble = task.exception()
    if trouble is not None:
        logger.error("проба моделей сорвалась", exc_info=trouble)


def _after(asked) -> int | None:
    """Номер, после которого страница хочет новое, приведённый к целому от нуля.

    **Пустота проходит пустотой, и это не то же самое, что ноль.** Так
    спрашивает страница, у которой номера ещё нет — только открылась или
    перезагрузилась; кольцо читает это как «с этого мига». Ноль значил бы «с
    самого начала», и окно мигнуло бы всем накопленным как свежим.

    Негодное и отрицательное читаются как ноль: страница присылает сюда то,
    что сама же получила прошлым ответом, и порча этого числа означает её
    собственную поломку, а не злой умысел. Отказ в ответ остановил бы её цикл
    совсем, а ноль всего лишь пришлёт уже виденное.

    Ноль здесь несущий, и потому отрицательное отсекается отдельно: кольцо
    считает потерянным всё, что старше названного номера, и на отрицательном
    объявляет потерю даже пустое. Ответ тогда приходит мгновенно, номер не
    двигается — и страница с мостом сходятся в плотную петлю без передышки.
    """
    if asked is None:
        return None
    return max(0, int_or_none(asked) or 0)
