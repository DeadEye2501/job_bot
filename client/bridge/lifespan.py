"""Жизнь моста при окне: от подъёма хозяйства до его гашения."""

from __future__ import annotations

import logging
from concurrent.futures import Future

from backend.telegram_login import TelegramLogin
from client.bridge.bot_stop import stop_bot
from client.bridge.hub import Hub
from client.bridge.journal import close_journal


logger = logging.getLogger(__name__)


_LOGIN_CLOSING_WAIT_S = 3.0
"""Сколько закрывающееся окно ждёт, пока вход отпустит сокет.

Короче, чем ждут бота: там останавливается целый обход, а здесь закрывается
одно соединение, которое к тому же чаще всего уже мертво. Ждать дольше значит
держать закрытие ради того, чего не будет.
"""

_CLOSING_WAIT_S = 5.0
"""Сколько закрывающееся окно ждёт остановки бота.

Меньше, чем ждут выход из учётной записи и снос (`bot_stop.STOP_TIMEOUT_S`):
там человек ждёт ответа на нажатие, а здесь смотрит на застывшее окно, которое
уже попросил закрыть. Срок уезжает доводом внутрь, а снаружи остаётся секунда
запаса — на случай, если мотор занят чужой работой.

Зависший обход переживёт оба срока: мотор гасит тот же, кто позвал `stop`, и
хвост подбирает `runner.stop()`.
"""


def start(runner, session_factory, rs, engine=None) -> Hub:
    """Собрать хозяйство окна и поднять под ним бота, если есть с чем.

    Бота поднимает окно, а не домен: он рождается и умирает вместе с окном, и
    домен, взявший его копию, держал бы вчерашнего.

    Движок приходит доводом от того, кто открывает окно: сносу без него не
    удалить файл базы — Windows держит открытый. Окна сегодня не существует
    вовсе, оно заводится слайсом А3 и зовёт отсюда обе двери, `start` и `stop`.
    """
    hub = Hub(runner, session_factory, rs)
    hub.engine = engine
    # Клиент входа свой, временный — отдельный от того, что поднимает бот
    # позже. Имя сеанса тоже своё: под общим они делили бы один файл.
    hub.login = TelegramLogin(
        "job_bot_relogin", rs, on_saved=lambda username: _remember_login(hub, username)
    )
    start_bot(hub)
    return hub


def stop(hub: Hub) -> None:
    """Отпустить всё, что держит закрывающееся окно: журнал, ждущих, вход и бота.

    Порядок в теле — от того, что перестаёт слушать, к тому, что перестаёт
    работать. Приёмник журнала снимается первым: кольцо записей одно на процесс
    и переживает окно, а оставленный приёмник держал бы через себя всё
    хозяйство. Ждущие запросы отпускаются вторыми — иначе последний из них
    догорал бы свой срок, держа на себе закрытие приложения.

    Недоведённый вход закрывается третьим. Посреди трёх шагов окно закрывают
    чаще, чем доводят их до конца: незакрытый клиент Pyrogram пережил бы и сам
    мотор, а несброшенный отпечаток кода увёл бы следующую попытку в «код уже
    отправлен».

    Идущий обход отменяется последним и с коротким сроком — иначе закрытие
    стояло бы столько, сколько осталось обходу, а человек уже нажал «закрыть».

    Звать это из потока мотора нельзя: работа, которой мы здесь ждём, идёт в
    нём же.
    """
    close_journal()
    hub.events.close()
    _forget_login(hub)
    bot = hub.bot
    bot_task = hub.bot_task
    if bot is None or bot_task is None:
        return
    try:
        hub.runner.submit(
            stop_bot(bot, bot_task, timeout=_CLOSING_WAIT_S)
        ).result(timeout=_CLOSING_WAIT_S + 1)
    except TimeoutError:
        logger.warning("закрытие: бот не остановился за %sс", _CLOSING_WAIT_S)
    except Exception:
        logger.exception("закрытие: остановка бота отказала")


def start_bot(hub: Hub) -> None:
    """Поднять бота, если приложение уже настроено, и промолчать, если нет.

    Зовут это трижды: при открытии окна, после удавшегося входа в Telegram и
    последним шагом первого запуска. Все три — мгновения, когда записанного
    могло стать достаточно, а другого повода поднять бота у приложения нет.

    Заслон обязателен. Собранный не вовремя бот отказывает броском
    (`Bot.__init__`), и отказ приезжает в журнал как «бот упал» — а случается
    он ровно посреди первого запуска, где вход идёт первым шагом, а модели
    вводят вторым и третьим. Человек читал бы о поломке приложения там, где всё
    идёт по плану.
    """
    if not _ready_for_bot(hub.rs):
        logger.info("бот ждёт настройки: нет учётной записи Telegram или модели")
        return
    _start_bot(hub)


def _ready_for_bot(rs) -> bool:
    """Хватает ли записанного, чтобы бот собрался.

    Те же три условия проверяет `Bot.__init__` и отвечает на нехватку броском —
    здесь они спрашиваются заранее, чтобы не звать заведомый отказ. У строки
    сеанса довод свой: без неё Pyrogram уходит спрашивать код через стандартный
    ввод, которого у оконной сборки нет, и приложение замирает молча.
    """
    return rs.has_tg_session and rs.chat is not None and rs.embed is not None


def _forget_login(hub: Hub) -> None:
    """Закрыть недоведённый вход, дождавшись, пока клиент отпустит сокет.

    Ждём, а не отпускаем вдогонку: следом гасится мотор, и незакрытый сокет
    пережил бы его. Ходим только когда есть что закрывать — попытки входа чаще
    нет вовсе.
    """
    login = hub.login
    if not getattr(login, "active", False):
        return
    try:
        hub.runner.submit(login.forget()).result(timeout=_LOGIN_CLOSING_WAIT_S)
    except Exception:
        logger.exception("закрытие: вход в Telegram не закрылся")


def _start_bot(hub: Hub) -> None:
    """Собрать бота и запустить его цикл внутри мотора.

    Собирается он там же, где работает, а не в потоке зовущего: хранилище
    сеанса у Pyrogram привязано к потоку, и собранный на чужом бот падал бы
    молча — исход корутины, отправленной на мотор, лежит в `Future`, которую
    без обработчика никто не читает.
    """

    async def _build_and_run() -> None:
        from backend.bot.client import Bot

        logger.info("собираем бота и запускаем его цикл")
        bot = Bot(hub.rs, hub.session_factory)
        _tell_the_window(bot, hub)
        hub.bot = bot
        await bot.run()

    future = hub.runner.submit(_build_and_run())
    future.add_done_callback(_log_if_crashed)
    hub.bot_task = future


def _tell_the_window(bot, hub: Hub) -> None:
    """Подписать очередь событий на всё, что бот делает сам по себе.

    Своего ответа у этих вестей нет: страница о них не спрашивала. Кладутся
    они из потока мотора, а забираются из потока окна, и очередь — то
    единственное место, где эти два потока встречаются законно.

    Пришедшее письмо кладёт две вести, а не одну. Первая про само письмо — по
    ней открытая переписка дописывает строку; вторая про счёт непрочитанного,
    и без неё счёт над списком рос бы только до ближайшей перезагрузки
    страницы: вниз его двигают домены той же вестью, а вверх не двигало бы
    ничто. Самого счёта в вести нет ни у кого — его страница спрашивает
    (`api.system.unread`).
    """
    events = hub.events

    def arrived(hr_id: int) -> None:
        events.add("contacts_hr_messages_arrived", {"hr_id": hr_id})
        events.add("unread_changed")

    bot.on_cycle_start = lambda: events.add("ingestion_started")
    bot.on_cycle_end = lambda: events.add("ingestion_finished")
    bot.on_progress = lambda stage, label, cur, tot: events.add(
        "progress_update",
        {"stage": stage, "label": label, "current": cur, "total": tot},
    )
    bot.on_new_message = arrived
    bot.on_hr_read = lambda hr_id, max_tg_id: events.add(
        "contacts_hr_read_receipt", {"hr_id": hr_id, "max_tg_id": max_tg_id}
    )
    bot.on_channels_changed = lambda: events.add("contacts_channels_changed")
    bot.on_contacts_changed = lambda: events.add("contacts_lists_changed")
    bot.on_vacancies_changed = lambda: events.add("vacancies_list_changed")


def _remember_login(hub: Hub, username: str | None) -> None:
    """Новый сеанс сохранён: запомнить ник и поднять бота, если он лежит.

    Не спросившийся ник (`None`) прежний в кэше не трогает: показать старый
    вернее, чем стереть его до первого удачного `get_me` у бота.
    """
    if username is not None:
        hub.username_cache = username
    if hub.bot is None:
        _start_bot(hub)


def _log_if_crashed(future: Future) -> None:
    """Сказать в журнал, что бот упал: без этого окно осталось бы живой ширмой.

    Отмену пропускаем: её приносит остановка мотора при закрытии окна, и
    жаловаться на неё значит писать беду о штатном выходе.
    """
    if future.cancelled():
        return
    error = future.exception()
    if error is not None:
        logger.critical("бот упал — окно осталось без него", exc_info=error)
