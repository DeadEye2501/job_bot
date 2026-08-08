"""Runtime settings layer.

Loads all mutable settings (TG account, LLM endpoints, pipeline tunables)
from SQLite into memory at startup. Sensitive values — TG api_hash and 2FA
password, the pyrogram session string, LLM api keys — go to and from the DB
through ``backend.crypto``; in this layer they are always plaintext.

Construct via ``await RuntimeSettings.load(session_factory)`` once at
startup. After the first-run wizard or any setting change, call
``await rs.reload()`` (or use the ``set_*`` methods which update both DB
and the cache).
"""

import logging
import math
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.crypto import decrypt_bytes, decrypt_str, encrypt_bytes, encrypt_str
from backend.models import (
    AppSetting,
    BotMode,
    BotState,
    LlmConfig,
    LlmConfigKind,
    TgAccount,
)


logger = logging.getLogger(__name__)


def _mask_phone(phone: str | None) -> str:
    """Безопасное представление phone для логов: показывает только last4
    для нормальных номеров (>=7 цифр), иначе полностью маскирует.
    Возвращает строку всегда, чтобы можно было передавать в %s без if'ов.
    """
    if not phone:
        return "***"
    if len(phone) < 7:
        return "***"
    return f"***{phone[-4:]}"


@dataclass(frozen=True)
class TgAccountConfig:
    api_id: int
    # Sensitive fields hidden from repr() so accidental logging never leaks them.
    api_hash: str = field(repr=False)
    phone: str
    password: str = field(repr=False)  # 2FA password; "" if none
    session_string: str | None = field(repr=False)  # pyrogram session; None pre-login


@dataclass(frozen=True)
class LlmProviderConfig:
    base_url: str
    # "" for endpoints that don't need auth (LM Studio / Ollama local).
    api_key: str = field(repr=False)
    model: str


# Defaults applied when an app_settings key is missing in the DB.
# Stored as strings (the table column is TEXT); typed at the property level.
_APP_DEFAULTS: dict[str, str] = {
    "scoring_threshold": "10",
    "poll_interval_sec": "1800",
    "backfill_limit": "15",
    "dm_backfill_limit": "50",
    "cv_path": "",
    "wizard_completed": "false",
    # send_locked: dev-safety, по дефолту блочит реальную отправку DM.
    # Раньше был hardcoded const в adapters/telegram.py — теперь
    # авторитет здесь, а telegram.SEND_LOCKED синкается из этой
    # настройки на старте Bot.run.
    "send_locked": "true",
    # auto_apply: kill-switch для автоматической отправки cover-letter'ов
    # из poll-цикла (auto-send branch в _parse_and_update_vacancy).
    # При False parse-pipeline всё равно отрабатывает — статус NEW,
    # ручная отправка из UI через «Отправить отклик» работает.
    "auto_apply": "true",
    # FX-rates для перевода salary в RUB при range-фильтрации. Раньше
    # были hardcoded 90/100 в backend/domain.py — устаревали без
    # возможности крутить. Юзер обновляет вручную через DBeaver когда
    # курс реально дрейфует за пределы своего bucket'а.
    "salary_usd_to_rub": "90",
    "salary_eur_to_rub": "100",
    # Cosine-similarity порог дедупа вакансий по embedding'ам. >= → считаем
    # дубликатом существующей вакансии и не парсим повторно. Слишком высокий
    # → дубли проскальзывают; слишком низкий → разные вакансии в одной
    # компании склеиваются. 0.92 — эмпирический baseline.
    "dedup_cosine_threshold": "0.92",
    # FloodWait-окно: Bot.send выписывает сюда момент, когда Telegram
    # разрешит снова слать (после полученного FloodWait-а). Дёргать
    # send_dm раньше — гарантированный повторный FloodWait и штраф.
    "flood_wait_until_ts": "0",            # epoch float — Bot.send не пытается до этого момента
}


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
            tg_row = (await session.scalars(select(TgAccount))).first()
            self._tg = _from_tg_row(tg_row) if tg_row else None

            chat_row = (
                await session.scalars(
                    select(LlmConfig).where(LlmConfig.kind == LlmConfigKind.CHAT)
                )
            ).first()
            self._chat = _from_llm_row(chat_row) if chat_row else None

            embed_row = (
                await session.scalars(
                    select(LlmConfig).where(LlmConfig.kind == LlmConfigKind.EMBED)
                )
            ).first()
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

    # === Read-only typed views ===

    @property
    def tg(self) -> TgAccountConfig | None:
        return self._tg

    @property
    def chat(self) -> LlmProviderConfig | None:
        return self._chat

    @property
    def embed(self) -> LlmProviderConfig | None:
        return self._embed

    @property
    def scoring_threshold(self) -> int:
        return int(self._app_value("scoring_threshold"))

    @property
    def poll_interval_sec(self) -> int:
        return int(self._app_value("poll_interval_sec"))

    @property
    def backfill_limit(self) -> int:
        """How many recent messages to scrape per Telegram channel poll."""
        return int(self._app_value("backfill_limit"))

    @property
    def dedup_cosine_threshold(self) -> float:
        """Cosine-порог дедупа в `cosine_top_match`. См. _APP_DEFAULTS.

        Clamp [0.5, 0.999]: 0.0 дропнул бы все вакансии как «дубликаты»
        (cosine ≥ 0 для нормированных векторов всегда), 1.0 эффективно
        выключил бы дедуп. NaN/Inf тоже отбиваем.
        """
        try:
            v = float(self._app_value("dedup_cosine_threshold"))
        except ValueError:
            return 0.92
        if not math.isfinite(v):
            return 0.92
        return max(0.5, min(0.999, v))

    @property
    def dm_backfill_limit(self) -> int:
        """How many recent DM messages to pull per HR on catch-up. Larger
        than the channel value so the offline-delete reconciliation window
        in `catch_up_missed_dms` is wide enough to cover edits/deletes the
        user made on another client while the bot was off."""
        return int(self._app_value("dm_backfill_limit"))

    @property
    def cv_path(self) -> str:
        return self._app_value("cv_path")

    @property
    def wizard_completed(self) -> bool:
        return self._app_value("wizard_completed").lower() == "true"

    @property
    def send_locked(self) -> bool:
        """Если True, реальная отправка Telegram-DM подавляется (для
        dev-тестов). Авторитетный источник — здесь; ``telegram.SEND_LOCKED``
        синкается с этой настройкой на старте Bot.run и при изменении
        через UI."""
        return self._app_value("send_locked").lower() == "true"

    @property
    def auto_apply(self) -> bool:
        """Если False, авто-отправка cover-letter'ов из poll-цикла
        отключена (parse-pipeline отрабатывает, ручная отправка через
        UI работает)."""
        return self._app_value("auto_apply").lower() == "true"

    @property
    def salary_usd_to_rub(self) -> int:
        try:
            v = int(self._app_value("salary_usd_to_rub"))
        except ValueError:
            return 90
        return v if v > 0 else 90

    @property
    def salary_eur_to_rub(self) -> int:
        try:
            v = int(self._app_value("salary_eur_to_rub"))
        except ValueError:
            return 100
        return v if v > 0 else 100

    @property
    def flood_wait_until_ts(self) -> float:
        try:
            return float(self._app_value("flood_wait_until_ts"))
        except ValueError:
            return 0.0

    def _app_value(self, key: str) -> str:
        # Treat NULL / empty / whitespace-only values in the DB as "not
        # set" so the default kicks in. Otherwise an empty value sneaking
        # in (manual SQL, a half-finished wizard) would crash the int(...)
        # casts in the numeric properties.
        raw = self._app.get(key, "")
        v = raw.strip() if raw else ""
        return v if v else _APP_DEFAULTS.get(key, "")

    # === Setters: write-through to DB and update the cache ===

    async def set_tg(
        self,
        *,
        api_id: int,
        api_hash: str,
        phone: str,
        password: str = "",
        session_string: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = (await session.scalars(select(TgAccount))).first()
                if row is None:
                    row = TgAccount(id=1)
                    session.add(row)
                row.api_id = api_id
                row.api_hash_encrypted = encrypt_str(api_hash)
                row.phone = phone
                row.password_encrypted = (
                    encrypt_str(password) if password else None
                )
                row.session_blob_encrypted = (
                    encrypt_bytes(session_string.encode("utf-8"))
                    if session_string is not None
                    else None
                )
        self._tg = TgAccountConfig(
            api_id=api_id,
            api_hash=api_hash,
            phone=phone,
            password=password,
            session_string=session_string,
        )
        # Phone в логах — last4, чтобы не утекало мобильное в plaintext.
        # api_hash / password / session_string наружу не пишем вовсе.
        logger.info(
            "Telegram credentials updated (api_id=%d, phone=%s, has_password=%s, has_session=%s)",
            api_id,
            _mask_phone(phone),
            bool(password),
            session_string is not None,
        )

    async def clear_tg(self) -> None:
        """Полное удаление TG-креденшалов: row в БД сносится, in-memory
        кэш обнуляется. Вызывается из logout — после этого сценарий
        первого захода (ввод api_id/api_hash/phone заново через UI).
        """
        async with self._session_factory() as session:
            async with session.begin():
                row = (await session.scalars(select(TgAccount))).first()
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
                row = (
                    await session.scalars(
                        select(LlmConfig).where(LlmConfig.kind == kind)
                    )
                ).first()
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

    async def set_app(self, key: str, value: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(AppSetting, key)
                if row is None:
                    session.add(AppSetting(key=key, value=value))
                else:
                    row.value = value
        self._app[key] = value
        # value намеренно не логируем — generic key/value setter, в любой
        # момент сюда могут пойти токены/секреты будущими callers'ами;
        # пишем только key + длину.
        logger.debug("app setting %s set (%d chars)", key, len(value or ""))

    async def mark_wizard_completed(self) -> None:
        await self.set_app("wizard_completed", "true")
        logger.info("First-run wizard completed")

    async def get_mode(self) -> BotMode:
        async with self._session_factory() as session:
            row = (await session.scalars(select(BotState))).first()
            return row.mode if row is not None else BotMode.OFF

    async def set_mode(self, mode: BotMode) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = (await session.scalars(select(BotState))).first()
                prev = row.mode.value if row is not None else None
                if row is None:
                    row = BotState(id=1, mode=mode)
                    session.add(row)
                else:
                    row.mode = mode
        if prev != mode.value:
            logger.info("Bot mode changed: %s -> %s", prev, mode.value)


def _from_tg_row(row: TgAccount) -> TgAccountConfig | None:
    if row.api_id is None or not row.api_hash_encrypted or not row.phone:
        return None
    return TgAccountConfig(
        api_id=row.api_id,
        api_hash=decrypt_str(row.api_hash_encrypted),
        phone=row.phone,
        password=(
            decrypt_str(row.password_encrypted) if row.password_encrypted else ""
        ),
        session_string=(
            decrypt_bytes(row.session_blob_encrypted).decode("utf-8")
            if row.session_blob_encrypted
            else None
        ),
    )


def _from_llm_row(row: LlmConfig) -> LlmProviderConfig | None:
    if not row.base_url or not row.model:
        return None
    return LlmProviderConfig(
        base_url=row.base_url,
        api_key=(
            decrypt_str(row.api_key_encrypted) if row.api_key_encrypted else ""
        ),
        model=row.model,
    )
