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

from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.crypto import decrypt_bytes, decrypt_str, encrypt_bytes, encrypt_str
from backend.models import (
    AppSetting,
    LlmConfig,
    LlmConfigKind,
    TgAccount,
)


logger = logging.getLogger(__name__)


def mask_phone(phone: str | None) -> str:
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
#
# Это единственное объявление умолчаний: засев кладёт в базу только то, что от
# них отличается, а окно настроек своих запасных чисел не держит вовсе.
_APP_DEFAULTS: dict[str, str] = {
    "scoring_threshold": "5",
    "poll_interval_sec": "1800",
    "backfill_limit": "15",
    "dm_backfill_limit": "50",
    "cv_path": "",
    "wizard_completed": "false",
    # send_locked: симуляция отправки — всё, кроме самого вызова Telegram.
    # По умолчанию выключена: включённая молча, она показывает «отклик
    # отправлен» над письмом, которого HR не получал, и вакансия при этом
    # закрывается от следующей попытки. Стенд включают нарочно, галкой в
    # настройках. Авторитет здесь, а telegram.SEND_LOCKED синкается из этой
    # настройки на старте Bot.run.
    "send_locked": "false",
    # auto_apply: kill-switch для автоматической отправки cover-letter'ов
    # из poll-цикла (auto-send branch в flows/parse.py, parse_and_update_vacancy).
    # При False parse-pipeline всё равно отрабатывает — статус NEW,
    # ручная отправка из UI через «Отправить отклик» работает.
    "auto_apply": "true",
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


def _log_tg_updated(
    api_id: int, phone: str, password: str, session_string: str | None
) -> None:
    """След смены учётной записи Telegram — без самих секретов.

    Номер пишется хвостом, чтобы мобильный не утекал в журнал открытым.
    Отпечаток приложения в журнал не идёт вовсе, а про пароль и строку
    сеанса говорится только «есть или нет».
    """
    logger.info(
        "Telegram credentials updated (api_id=%d, phone=%s, has_password=%s, has_session=%s)",
        api_id,
        mask_phone(phone),
        bool(password),
        session_string is not None,
    )


async def _tg_row(session: AsyncSession) -> TgAccount | None:
    """Единственная строка учётной записи Telegram, если она заведена."""
    return (await session.scalars(select(TgAccount))).first()


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
            tg_row = await _tg_row(session)
            self._tg = _from_tg_row(tg_row) if tg_row else None

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
        return self._app_value("cv_path")

    @property
    def wizard_completed(self) -> bool:
        return self._app_bool("wizard_completed")

    @property
    def send_locked(self) -> bool:
        """Если True, реальная отправка Telegram-DM подавляется — стенд, на
        котором конвейер обкатывают без живых HR. По умолчанию False.
        Авторитетный источник — здесь; ``telegram.SEND_LOCKED`` синкается с
        этой настройкой на старте Bot.run и при изменении через UI."""
        return self._app_bool("send_locked")

    @property
    def auto_apply(self) -> bool:
        """Если False, авто-отправка cover-letter'ов из poll-цикла
        отключена (parse-pipeline отрабатывает, ручная отправка через
        UI работает)."""
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

    def _app_number(self, key: str, read, kind):
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
                row = await _tg_row(session)
                if row is None:
                    row = TgAccount(id=1)
                    session.add(row)
                row.api_id = creds.api_id
                row.api_hash_encrypted = encrypt_str(creds.api_hash)
                row.phone = creds.phone
                row.password_encrypted = (
                    encrypt_str(creds.password) if creds.password else None
                )
                row.session_blob_encrypted = (
                    encrypt_bytes(creds.session_string.encode("utf-8"))
                    if creds.session_string is not None
                    else None
                )
        self._tg = creds
        _log_tg_updated(
            creds.api_id, creds.phone, creds.password, creds.session_string
        )

    async def clear_tg(self) -> None:
        """Полное удаление TG-креденшалов: row в БД сносится, in-memory
        кэш обнуляется. Вызывается из logout — после этого сценарий
        первого захода (ввод api_id/api_hash/phone заново через UI).
        """
        async with self._session_factory() as session:
            async with session.begin():
                row = await _tg_row(session)
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


def _from_tg_row(row: TgAccount) -> TgAccountConfig | None:
    """Учётные данные Telegram из строки базы; `None`, если их нет.

    Нечитаемый шифротекст — тоже «нет»: связка ключей ОС и база разъезжаются
    при чистке связки, переносе профиля и восстановлении из копии, а брошенный
    отсюда отказ не ловит никто — приложение падает раньше окна.
    """
    if row.api_id is None or not row.api_hash_encrypted or not row.phone:
        return None
    try:
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
    except InvalidToken:
        logger.exception("Telegram credentials are unreadable, treating as unset")
        return None


def _from_llm_row(row: LlmConfig) -> LlmProviderConfig | None:
    """Настройки провайдера из строки базы; `None`, если их нет.

    Нечитаемый ключ — тоже «нет», по причине из `_from_tg_row`.
    """
    if not row.base_url or not row.model:
        return None
    try:
        return LlmProviderConfig(
            base_url=row.base_url,
            api_key=(
                decrypt_str(row.api_key_encrypted) if row.api_key_encrypted else ""
            ),
            model=row.model,
        )
    except InvalidToken:
        logger.exception("LLM provider key is unreadable, treating as unset")
        return None
