"""Экран «Настройки»: всё, что окно спрашивает и правит на нём."""

from __future__ import annotations

import asyncio
import logging

from adapters.browser import find_browser
from backend.provider_config import LlmProviderConfig
from backend.telegram_login import username_of
from backend.agent.availability import agent_refusal
from client.bridge.answer import BAD_PAYLOAD, Denied, denied, reply
from client.bridge.bot_stop import detach_bot, stop_bot
from client.bridge.hub import Hub
from client.bridge.llm import PROVIDER_KINDS, Llm, read_llm_creds
from client.bridge.login import Login
from client.bridge.mail import Mail
from client.bridge.wire import _llm_provider_to_dict, _tg_creds_to_dict


logger = logging.getLogger(__name__)

_CONNECT_TRIES = 15
_CONNECT_STEP_S = 0.2
"""Сколько ждать соединения бота, прежде чем спрашивать у него ник.

На холодном старте Pyrogram читает сеанс и соединяется пару секунд, а экран
настроек спрашивают раньше. Три секунды — заведомо больше обычного соединения и
заведомо меньше того, за что человек считает экран повисшим.
"""

APP_KEYS = (
    "scoring_threshold",
    "poll_interval_sec",
    "backfill_limit",
    "dm_backfill_limit",
    "auto_apply",
    "aggregator_backfill_limit",
    "show_browser",
    "letter_writer",
)
"""Что окну позволено писать в настройки приложения.

Перечнем, а не как придётся: опечатка в имени легла бы в настройки своим
ключом и осталась бы там навсегда, никем не читаемая.
"""


class Settings(Login, Llm, Mail):
    """Настройки времени выполнения, какими их правит окно.

    Разрезано на четыре файла по ответственности: сами настройки здесь, вход в
    Telegram, разговор с поставщиком модели и почта для откликов — у примесей
    рядом. Поверхность у них при этом одна: окно видит один экран настроек, и примесь
    здесь — способ разложить этот экран по файлам, а не задел под вторую
    реализацию.

    Секреты: снимок настроек отдаёт ключи доступа к моделям и `api_hash`
    Telegram как есть — окно умеет показать их по нажатию, а живёт оно своим
    окном и в сеть не выходит.
    """

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def get(self) -> dict:
        """Снимок настроек: учётная запись Telegram, обе модели, пороги отбора.

        Ник вошедшего спрашивается у Telegram, а не берётся из настроек: там
        его нет вовсе, он живёт у самой учётной записи.
        """

        async def run() -> dict:
            rs = self._hub.rs
            tg = rs.tg
            browser = find_browser()
            return {
                "tg": {
                    **_tg_creds_to_dict(tg),
                    "has_password": bool(tg and tg.password),
                    "has_session": rs.has_tg_session,
                    "username": await self._username(),
                },
                "chat": _llm_provider_to_dict(rs.chat),
                "embed": _llm_provider_to_dict(rs.embed),
                "pipeline": {
                    "scoring_threshold": rs.scoring_threshold,
                    "poll_interval_sec": rs.poll_interval_sec,
                    "backfill_limit": rs.backfill_limit,
                    "dm_backfill_limit": rs.dm_backfill_limit,
                    "auto_apply": rs.auto_apply,
                },
                "aggregators": {
                    "aggregator_backfill_limit": rs.aggregator_backfill_limit,
                    "show_browser": rs.show_browser,
                    "letter_writer": rs.letter_writer,
                    "lock": agent_refusal(rs.chat, browser),
                    "browser": browser.name if browser else None,
                },
            }

        return reply(self._hub.runner, run())

    def save(self, payload: dict | None = None) -> dict:
        """Записать присланную часть настроек: поставщиков и пороги отбора.

        Нагрузка — словарь с любыми из ключей `chat`, `embed` и `app`;
        пропущенный значит «не трогать». Ответ называет применённое поимённо —
        нынешний экран этот перечень выбрасывает и читает только исход, но
        экран пишется заново (Б2), и различить «записали поставщика» от
        «записали пороги» будет нечем, кроме него.
        """
        # Не-объект сводится к пустоте, а не роняет разбор: спотыкался бы он до
        # мотора, мимо конверта, прямо в канал.
        payload = payload if isinstance(payload, dict) else {}
        try:
            creds = _read_providers(payload)
        except ValueError as e:
            return denied(str(e))

        app = payload.get("app")
        app = app if isinstance(app, dict) else None

        async def run() -> dict:
            applied = await self._apply_providers(creds)
            if app is not None:
                try:
                    await self._apply_app(app, applied)
                except Exception:
                    # Окну в этот миг едет «сорвалось» без подробностей, и без
                    # этой строки разобрать, что успело лечь в настройки, было
                    # бы нечем вовсе.
                    logger.exception("настройки: записано %s, дальше сорвалось", applied)
                    raise
            return {"applied": applied}

        return reply(self._hub.runner, run())

    def logout(self) -> dict:
        """Выйти из Telegram: отпустить бота и стереть учётную запись.

        Порядок шагов важен. Сперва закрывается недоведённый вход — открытое
        окно повторного входа иначе оставит после себя «код уже отправлен».
        Потом бот просит Telegram отозвать ключ на сервере и останавливается:
        останься он работать, следующий его запрос ушёл бы с учётными данными,
        которых в настройках уже нет. И только после этого стирается сеанс,
        отчего экран и лампочка показывают «нет сессии».

        Не отозвавшийся ключ учётную запись не стирает. Сеанс на серверах
        Telegram живёт дальше и продолжает читать переписку; стерев настройки,
        мы оставили бы человека уверенным в обратном — и отозвать ключ было бы
        уже нечем, строки сеанса в настройках не осталось бы.
        """
        bot, bot_task = detach_bot(self._hub)

        async def run() -> dict:
            await self._hub.login.forget()
            try:
                await stop_bot(
                    bot, bot_task, bot.log_out_session if bot is not None else None
                )
            except Exception as e:
                logger.exception("выход: ключ на сервере не отозван")
                raise Denied(
                    "Telegram не отозвал ключ, учётная запись осталась на месте. "
                    f"Попробуйте ещё раз: {type(e).__name__}: {e}"
                ) from e
            if bot is None:
                _check_logout_without_bot(self._hub.rs.has_tg_session)
            await self._hub.rs.clear_tg()
            self._hub.username_cache = ""
            return {}

        return reply(self._hub.runner, run())

    def cancel_login(self) -> dict:
        """Человек закрыл окно повторного входа, не доведя его.

        Временный клиент Telegram закрывается, а шаг обнуляется: иначе остаётся
        открытый сокет, а следующая попытка упирается в «код уже отправлен».

        Незаведённую попытку на мотор не отправляем: окно закрывают и не начав
        входить, а зов туда стоит целого круга по мотору и ждёт ответа своим
        сроком — ради работы, которой нет.
        """
        if not self._hub.login.active:
            return {"ok": {}}

        async def run() -> dict:
            await self._hub.login.forget()
            return {}

        return reply(self._hub.runner, run())

    async def _username(self) -> str:
        """Ник вошедшего: спросить Telegram, а не вышло — отдать запомненный.

        Запомненный нужен потому, что бот поднимается медленно, а экран
        настроек спрашивают сразу после входа: без него человек видел бы пустое
        поле там, где только что вошёл под своим именем.
        """
        client = getattr(self._hub.bot, "client", None)
        await _wait_connected(client)
        asked = None
        if getattr(client, "is_connected", False):
            asked = await username_of(client)
            if asked is None:
                # Без трассировки: беду поймал и записал сам `username_of`,
                # а здесь живого исключения нет — вышло бы «NoneType: None».
                logger.warning("ник для настроек спросить не вышло")
        if asked is None:
            return self._hub.username_cache
        # Пустая строка — это ответ «ника нет», и он перебивает запомненное:
        # снятый ник иначе остался бы на экране прежним.
        self._hub.username_cache = asked
        return asked

    async def _apply_providers(self, creds: dict[str, LlmProviderConfig]) -> list[str]:
        """Записать присланных поставщиков и назвать записанных."""
        setters = {"chat": self._hub.rs.set_chat, "embed": self._hub.rs.set_embed}
        applied: list[str] = []
        for kind, cfg in creds.items():
            await setters[kind](
                base_url=cfg.base_url, api_key=cfg.api_key, model=cfg.model
            )
            applied.append(kind)
        return applied

    async def _apply_app(self, app: dict, applied: list[str]) -> None:
        """Записать пороги отбора, дописывая записанные в общий перечень.

        Перечень приходит доводом, а не заводится здесь: записи идут по одной, и
        поломка посреди застаёт часть уже записанной. Свой список умер бы вместе
        с броском, и жалоба зовущего назвала бы только поставщиков — то есть
        ровно не то, на чём сорвалось. По той же причине он и не возвращается:
        читать возврат некому — зовущий держит тот же самый список.
        """
        for key, value in app.items():
            if key not in APP_KEYS:
                logger.warning("настройки: незнакомый ключ %r пропущен", key)
                continue
            # Да/нет едет как есть — в слово его переводят настройки; прочее
            # хранится строкой.
            await self._hub.rs.set_app(str(key), value if isinstance(value, bool) else str(value))
            applied.append(f"app.{key}")




def _check_logout_without_bot(has_session: bool) -> None:
    """Можно ли стирать учётную запись, когда бота нет вовсе.

    Сеанс есть, а бота нет — отзывать ключ нечем: для этого нужен живой клиент.
    Стереть настройки сейчас значило бы сказать «вышли» там, где сеанс на
    серверах Telegram жив и продолжает читать переписку, а отзывать его стало
    бы нечем: строки сеанса в настройках не осталось бы.

    Нет ни бота, ни сеанса — отзывать было нечего, и настройки стираются:
    иначе выйти было бы нельзя вовсе.
    """
    if has_session:
        logger.warning("выход без бота при живом сеансе: ключ не отозван")
        raise Denied(
            "Бот не поднят — отозвать ключ нечем, а без этого сеанс "
            "на серверах Telegram останется жив. Дождитесь связи "
            "или перезапустите приложение и попробуйте снова."
        )
    logger.warning("выход без поднятого бота: отзывать было нечего")


async def _wait_connected(client) -> None:
    """Короткое ожидание соединения бота — до трёх секунд."""
    if client is None:
        return
    for _ in range(_CONNECT_TRIES):
        if getattr(client, "is_connected", False):
            return
        await asyncio.sleep(_CONNECT_STEP_S)


def _read_providers(payload: dict) -> dict[str, LlmProviderConfig]:
    """Учётные данные обоих поставщиков — до записи и тем же правилом, что проба.

    Пустое поле почти всегда стёрлось последним переводом фокуса. Уйди оно в
    запись, поставщик пропал бы с экрана целиком — из пустоты его собрать
    нечем, — и человек считал бы, что починилось, пока не упал первый разбор
    вакансии.

    Отказ называет поставщика: экран правит обоих сразу, и без имени человек не
    знает, в каком из двух полей стёрлось.
    """
    creds: dict[str, LlmProviderConfig] = {}
    for kind in PROVIDER_KINDS:
        draft = payload.get(kind)
        if not isinstance(draft, dict):
            continue
        try:
            creds[kind] = read_llm_creds(draft, kind)
        except BAD_PAYLOAD as e:
            raise ValueError(f"{kind}: {e}") from e
    return creds
