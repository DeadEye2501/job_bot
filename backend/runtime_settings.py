"""Runtime settings layer.

Loads all mutable settings (TG account, LLM endpoints, pipeline tunables)
from SQLite into memory at startup. Sensitive values — LLM api keys here, the
Telegram secrets in ``backend.tg_credentials`` — go to and from the DB through
``backend.crypto``; in this layer they are always plaintext.

Construct via ``await RuntimeSettings.load(session_factory)`` once at
startup. After the first-run wizard or any setting change, call
``await rs.reload()`` (or use the ``set_*`` methods which update both DB
and the cache).
"""

import logging
import math
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.crypto import decrypt_or_none, encrypt_str
from backend.incoming import normalize_enum
from backend.provider_config import LlmProviderConfig, provider_complete
from backend.repository.app_settings import CV_PATH_KEY, put_app_setting
from backend.models import (
    AppSetting,
    LlmConfig,
    LlmConfigKind,
    TgAccount,
)
from backend.tg_credentials import (
    TgAccountConfig,
    fill_tg_row,
    from_tg_row,
    log_tg_updated,
    tg_row,
)


logger = logging.getLogger(__name__)


# Defaults applied when an app_settings key is missing in the DB.
# Stored as strings (the table column is TEXT); typed at the property level.
#
# Это единственное объявление умолчаний: засев кладёт в базу только то, что от
# них отличается, а окно настроек своих запасных чисел не держит вовсе.
_APP_DEFAULTS: dict[str, str] = {
    "scoring_threshold": "5",
    "poll_interval_sec": "1800",
    "backfill_limit": "15",
    "dm_backfill_limit": "50",
    CV_PATH_KEY: "",
    "wizard_completed": "false",
    # send_locked: симуляция отправки — всё, кроме самого вызова Telegram.
    # По умолчанию выключена: включённая молча, она показывает «отклик
    # отправлен» над письмом, которого HR не получал, и вакансия при этом
    # закрывается от следующей попытки. Окно её не пишет: стенд включают
    # нарочно, записью в базу. Авторитет здесь, а telegram.SEND_LOCKED зеркалится из этой
    # настройки на старте Bot.run и на каждой её записи (`set_app`).
    "send_locked": "false",
    # auto_apply: передаётся ли разобранное откликателю (`flows/handover`).
    # Ручной отклик зовёт откликатель мимо передачи, и эта настройка его не
    # касается.
    "auto_apply": "true",
    # Cosine-similarity порог дедупа вакансий по embedding'ам. >= → считаем
    # дубликатом существующей вакансии и не парсим повторно. Слишком высокий
    # → дубли проскальзывают; слишком низкий → разные вакансии в одной
    # компании склеиваются. 0.92 — эмпирический baseline.
    "dedup_cosine_threshold": "0.92",
    # FloodWait-окно: откликатель (`applying/telegram_ban`) выписывает сюда
    # момент, когда Telegram разрешит снова слать, и до него Telegram в
    # способах не предлагает (`applying/world`). Дёргать send_dm раньше —
    # гарантированный повторный FloodWait и штраф.
    "flood_wait_until_ts": "0",            # epoch float
    "aggregator_backfill_limit": "20",
    "show_browser": "false",
    "letter_writer": "app",
    # Общие выключатели источников одного рода — над тумблерами строк, а не
    # вместо них: выключенный гасит общий обход, строки помнят своё.
    "channels_enabled": "true",
    "aggregators_enabled": "true",
}

LETTER_WRITERS = ("app", "agent")
"""Кто пишет письмо для откликов вне Telegram: чат-модель приложения или агент.
Набор объявлен один раз: всё, что различает автора письма, берёт значения отсюда."""


async def _llm_row(session: AsyncSession, kind: LlmConfigKind) -> LlmConfig | None:
    """Строка настроек поставщика моделей своего рода, если она заведена."""
    return (
        await session.scalars(select(LlmConfig).where(LlmConfig.kind == kind))
    ).first()


class RuntimeSettings:
    """In-memory cache of runtime settings, backed by SQLite."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory
        self._tg: TgAccountConfig | None = None
        self._chat: LlmProviderConfig | None = None
        self._embed: LlmProviderConfig | None = None
        self._app: dict[str, str] = {}

    @classmethod
    async def load(
        cls, session_factory: async_sessionmaker[AsyncSession]
    ) -> "RuntimeSettings":
        rs = cls(session_factory)
        await rs.reload()
        return rs

    async def reload(self) -> None:
        async with self._session_factory() as session:
            tg = await tg_row(session)
            self._tg = from_tg_row(tg) if tg else None

            chat_row = await _llm_row(session, LlmConfigKind.CHAT)
            self._chat = _from_llm_row(chat_row) if chat_row else None

            embed_row = await _llm_row(session, LlmConfigKind.EMBED)
            self._embed = _from_llm_row(embed_row) if embed_row else None

            self._app = {
                s.key: (s.value or "")
                for s in (await session.scalars(select(AppSetting))).all()
            }
        logger.debug(
            "Runtime settings reloaded: tg=%s chat=%s embed=%s app_keys=%d",
            self._tg is not None,
            self._chat is not None,
            self._embed is not None,
            len(self._app),
        )

    @property
    def tg(self) -> TgAccountConfig | None:
        return self._tg

    @property
    def has_tg_session(self) -> bool:
        """Есть ли сохранённая строка сеанса Telegram.

        Спрашивают об этом четверо и по разным поводам — можно ли поднимать
        бота, засчитан ли первый шаг мастера, что показать на экране настроек,
        сносить ли устаревшие файлы сеанса при запуске, — а условие у всех одно,
        и написанное порознь оно разъезжается: учётные данные без сеанса
        выглядят как готовый вход, но подключиться с ними нельзя.
        """
        return self._tg is not None and bool(self._tg.session_string)

    @property
    def chat(self) -> LlmProviderConfig | None:
        return self._chat

    @property
    def embed(self) -> LlmProviderConfig | None:
        return self._embed

    @property
    def scoring_threshold(self) -> int:
        return self._app_int("scoring_threshold")

    @property
    def poll_interval_sec(self) -> int:
        return self._app_int("poll_interval_sec", minimum=1)

    @property
    def backfill_limit(self) -> int:
        """How many recent messages to scrape per Telegram channel poll."""
        return self._app_int("backfill_limit", minimum=1)

    @property
    def aggregator_backfill_limit(self) -> int:
        """Сколько новых для базы вакансий искатель передаёт в конвейер за обход
        одного источника."""
        return self._app_int("aggregator_backfill_limit", minimum=1)

    @property
    def channels_enabled(self) -> bool:
        """Общий обход каналов разрешён. Ручной прогон одного канала его не спрашивает."""
        return self._app_bool("channels_enabled")

    @property
    def aggregators_enabled(self) -> bool:
        """Общий обход агрегаторов разрешён. Ручной обход и вход его не спрашивают."""
        return self._app_bool("aggregators_enabled")

    @property
    def show_browser(self) -> bool:
        """Браузер виден всё время; выключено — только на капче и входе."""
        return self._app_bool("show_browser")

    @property
    def letter_writer(self) -> str:
        """Кто пишет письмо для откликов вне Telegram: `app` или `agent`.

        Чужое слово читается как умолчание: письмо без автора не ушло бы вовсе.
        """
        return (
            normalize_enum(self._app_value("letter_writer"), LETTER_WRITERS)
            or _APP_DEFAULTS["letter_writer"]
        )

    @property
    def dedup_cosine_threshold(self) -> float:
        """Cosine-порог дедупа в `cosine_top_match`. См. _APP_DEFAULTS.

        Clamp [0.5, 0.999]: 0.0 дропнул бы все вакансии как «дубликаты»
        (cosine ≥ 0 для нормированных векторов всегда), 1.0 эффективно
        выключил бы дедуп. NaN/Inf тоже отбиваем.
        """
        return max(0.5, min(0.999, self._app_float("dedup_cosine_threshold")))

    @property
    def dm_backfill_limit(self) -> int:
        """How many recent DM messages to pull per HR on catch-up. Larger
        than the channel value so the offline-delete reconciliation window
        in `catch_up_missed_dms` is wide enough to cover edits/deletes the
        user made on another client while the bot was off."""
        return self._app_int("dm_backfill_limit", minimum=1)

    @property
    def cv_path(self) -> str:
        return self._app_value(CV_PATH_KEY)

    @property
    def wizard_completed(self) -> bool:
        return self._app_bool("wizard_completed")

    @property
    def send_locked(self) -> bool:
        """Если True, реальная отправка Telegram-DM подавляется — стенд, на
        котором конвейер обкатывают без живых HR. По умолчанию False.
        Авторитетный источник — здесь; ``telegram.SEND_LOCKED`` зеркалится с
        этой настройки на старте Bot.run и на каждой её записи, кто бы её ни
        писал."""
        return self._app_bool("send_locked")

    @property
    def auto_apply(self) -> bool:
        """Передаётся ли разобранное откликателю; выключено — только разбор."""
        return self._app_bool("auto_apply")

    @property
    def flood_wait_until_ts(self) -> float:
        return self._app_float("flood_wait_until_ts")

    def _app_bool(self, key: str) -> bool:
        """Булева настройка; истина — только слово «true» в любом регистре.

        Что считать истиной, договорено здесь один раз на всех: значения
        правят руками через DBeaver, и напиши кто-то «1» или «yes» — три
        настройки ответили бы одинаково лишь потому, что писались за один
        раз одним человеком.
        """
        return self._app_value(key).lower() == "true"

    def _app_float(self, key: str) -> float:
        """Дробная настройка; негодное значение откатывается к умолчанию.

        Бесконечность и `NaN` негодны наравне с буквами: они «числа», но ни
        один зовущий их не переживёт — порог дедупа с ними отсеял бы всё или
        ничего, а метка времени ожидания заперла бы отправку навсегда.

        Дальнейшие оговорки — зажим у порога — остаются зовущему.
        """
        def read(raw: str) -> float | None:
            try:
                value = float(raw)
            except ValueError:
                return None
            return value if math.isfinite(value) else None

        return self._app_number(key, read, float)

    def _app_int(self, key: str, *, minimum: int | None = None) -> int:
        """Целая настройка; негодное значение откатывается к умолчанию.

        Нижняя граница задаётся не всем: у порога оценки годится любое целое,
        потому что и сам счёт бывает отрицательным, и «пропускать всё»
        выражается именно отрицательным порогом.
        """
        def read(raw: str) -> int | None:
            try:
                value = int(raw)
            except ValueError:
                return None
            return None if minimum is not None and value < minimum else value

        return self._app_number(key, read, int)

    def _app_number(self, key: str, read: Callable, kind: type):
        """Числовая настройка: прочитанное или умолчание, с жалобой в журнал.

        Что считать годным, решает `read` — у целых и дробных это разные
        вопросы. Общее у них — что делать с негодным: значения правят руками
        через DBeaver, и опечатка вроде «1 800» не должна ронять запуск.
        Умолчание берётся из общего перечня: два места, знающих одно и то же
        число, разошлись бы молча.
        """
        raw = self._app_value(key)
        value = read(raw)
        if value is None:
            logger.warning(
                "настройка %s негодна (%r) — беру умолчание", key, raw
            )
            return kind(_APP_DEFAULTS[key])
        return value

    def _app_value(self, key: str) -> str:
        # Treat NULL / empty / whitespace-only values in the DB as "not
        # set" so the default kicks in. Otherwise an empty value sneaking
        # in (manual SQL, a half-finished wizard) would crash the int(...)
        # casts in the numeric properties.
        raw = self._app.get(key, "")
        v = raw.strip() if raw else ""
        return v if v else _APP_DEFAULTS.get(key, "")

    async def set_tg(self, creds: TgAccountConfig) -> None:
        """Записать учётные данные Telegram и запомнить их в кэше.

        Приходят они свёрткой, а не россыпью доводов: пять значений здесь —
        одна учётная запись, и порознь ни одно из них строку не составляет.
        Умолчаний у полей нет нарочно: пустой пароль и пустая строка сеанса
        стирают записанный секрет, и пропустить их молча значит разлогинить
        человека мимо его воли.
        """
        async with self._session_factory() as session:
            async with session.begin():
                row = await tg_row(session)
                if row is None:
                    row = TgAccount(id=1)
                    session.add(row)
                fill_tg_row(row, creds)
        self._tg = creds
        log_tg_updated(
            creds.api_id, creds.phone, creds.password, creds.session_string
        )

    async def clear_tg(self) -> None:
        """Полное удаление TG-креденшалов: row в БД сносится, in-memory
        кэш обнуляется. Вызывается из logout — после этого сценарий
        первого захода (ввод api_id/api_hash/phone заново через UI).
        """
        async with self._session_factory() as session:
            async with session.begin():
                row = await tg_row(session)
                if row is not None:
                    await session.delete(row)
        self._tg = None
        logger.info("Telegram credentials cleared")

    async def set_chat(
        self, *, base_url: str, api_key: str, model: str
    ) -> None:
        await self._set_llm(LlmConfigKind.CHAT, base_url, api_key, model)

    async def set_embed(
        self, *, base_url: str, api_key: str, model: str
    ) -> None:
        await self._set_llm(LlmConfigKind.EMBED, base_url, api_key, model)

    async def _set_llm(
        self,
        kind: LlmConfigKind,
        base_url: str,
        api_key: str,
        model: str,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await _llm_row(session, kind)
                if row is None:
                    row = LlmConfig(kind=kind)
                    session.add(row)
                row.base_url = base_url
                row.api_key_encrypted = (
                    encrypt_str(api_key) if api_key else None
                )
                row.model = model
        cfg = LlmProviderConfig(base_url=base_url, api_key=api_key, model=model)
        if kind is LlmConfigKind.CHAT:
            self._chat = cfg
        else:
            self._embed = cfg
        # api_key намеренно не логируем; base_url / model / has_key достаточно
        # для диагностики «не тот провайдер / модель».
        logger.info(
            "LLM config updated: kind=%s base_url=%s model=%s has_key=%s",
            kind.value,
            base_url,
            model,
            bool(api_key),
        )

    async def set_app(self, key: str, value: str | bool | int) -> None:
        """Записать настройку строкой; да/нет ложится словом, по которому его
        читает `_app_bool`. Приводит здесь, а не каждый пишущий у себя:
        `str(True)` дал бы «True», и сравнение с «true» его не прошло бы."""
        value = ("true" if value else "false") if isinstance(value, bool) else str(value)
        async with self._session_factory() as session:
            async with session.begin():
                await put_app_setting(session, key, value)
        self._app[key] = value
        if key == "send_locked":
            # Заслон на горячем пути сверяется своей копией — читать настройки
            # на каждое письмо незачем, — и без этой строки запрет начал бы
            # действовать только после перезапуска бота: запрет записан, а
            # следующий отклик всё равно уходит живому HR. Зеркалит владелец
            # настройки, а не тот, кто её пишет: копия у транспорта одна.
            from adapters import telegram
            telegram.SEND_LOCKED = self.send_locked
        # value намеренно не логируем — generic key/value setter, в любой
        # момент сюда могут пойти токены/секреты будущими callers'ами;
        # пишем только key + длину.
        logger.debug("app setting %s set (%d chars)", key, len(value or ""))

    async def mark_wizard_completed(self) -> None:
        await self.set_app("wizard_completed", True)
        logger.info("First-run wizard completed")


def _from_llm_row(row: LlmConfig) -> LlmProviderConfig | None:
    """Настройки провайдера из строки базы; `None`, если их нет.

    Нечитаемый ключ — тоже «нет», по причине из `decrypt_or_none`.
    """
    if not provider_complete(row.kind.value, row.base_url, row.model):
        return None
    api_key = decrypt_or_none(row.api_key_encrypted, "LLM provider key")
    if api_key is None:
        return None
    return LlmProviderConfig(
        base_url=row.base_url or "", api_key=api_key, model=row.model,
    )
