"""Что окно делает с каналом: опрос, курсор, чёрный список, состав."""

from __future__ import annotations

import json

from PySide6.QtCore import Signal, Slot

from backend.domain.telegram_identity import normalize_username
from backend.models import TelegramChannel
from backend.repository import blacklist, channels as channels_repo
from client.bridge.answer import _err, _ok
from client.bridge.payload import _log_invalid_payload


class ChannelActionSlots:
    """Правки над каналом — всё, чем окно его трогает, а не показывает.

    Подмешивающий обязан держать `_bot`, `_session_factory`, `_dispatch` и
    `_dispatch_action`, а сверх того — сигнал `contacts_lists_changed`, которым
    окно узнаёт, что списки надо перечитать целиком.

    Сигнал `contacts_channels_changed` объявлен здесь, а испускает его бот:
    каналы меняются и сами по себе, когда сбор находит новый.
    """

    contacts_channel_action_done = Signal(str)
    contacts_channels_changed = Signal()

    @Slot(int)
    def contacts_add_channel_to_blacklist(self, channel_id: int) -> None:
        """Insert kind="channel" blacklist row for this channel.
        Value = `@{username}`. Idempotent (re-activates inactive row).
        Pushes contacts_lists_changed so
        cross-tab `is_blacklisted` flags refresh.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                ch = await session.get(TelegramChannel, channel_id)
                if ch is None:
                    return _err("Канал не найден.", channel_id=channel_id, action="blacklist")
                value = channels_repo.channel_blacklist_preferred_value(ch)
                if value is None:
                    return _err(
                        "У канала нет @username.",
                        channel_id=channel_id, action="blacklist",
                    )
                _, outcome = await blacklist.create_blacklist(
                    session, kind="channel", value=value,
                )
                # Канал в blacklist → автоматически выключаем сам канал,
                # чтобы UI-toggle отражал реальное «канал не работает».
                if ch.is_active:
                    ch.is_active = False
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "blacklist",
                "channel_id": channel_id,
                "value": value,
                "existed": outcome != "created",
                "was_inactive": outcome == "reactivated",
            })

        self._dispatch(self.contacts_channel_action_done, run())

    @Slot(int)
    def contacts_remove_channel_from_blacklist(self, channel_id: int) -> None:
        """Deactivate any kind="channel" blacklist row for this channel."""
        async def run() -> str:
            async with self._session_factory() as session:
                ch = await session.get(TelegramChannel, channel_id)
                if ch is None:
                    return _err("Канал не найден.", channel_id=channel_id, action="unblacklist")
                candidates = channels_repo.channel_blacklist_candidates(ch)
                if not candidates:
                    return _err(
                        "У канала нет @username.",
                        channel_id=channel_id, action="unblacklist",
                    )
                updated = await blacklist.deactivate_blacklist_values(
                    session, "channel", candidates,
                )
                await session.commit()
            self.contacts_lists_changed.emit()
            return _ok({
                "action": "unblacklist",
                "channel_id": channel_id,
                "updated": updated,
            })

        self._dispatch(self.contacts_channel_action_done, run())

    @Slot(int)
    def request_channel_poll_now(self, channel_id: int) -> None:
        """UI «Прогнать сейчас» — single-channel poll."""
        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", channel_id=channel_id, action="poll_now")
            status = await self._bot.poll_channel_now(channel_id)
            if status == "ok":
                return _ok({
                    "channel_id": channel_id,
                    "action": "poll_now",
                    "status": status,
                })
            messages = {
                "busy": "Уже идёт другой цикл, попробуйте позже.",
                "missing": "Канал не найден или без @username.",
                "cancelled": "Поллинг канала отменён.",
                "error": "Не удалось прогнать канал — см. логи.",
            }
            return _err(
                messages.get(status, "Не удалось прогнать канал."),
                channel_id=channel_id,
                action="poll_now",
                status=status,
            )

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="poll_now", channel_id=channel_id,
        )

    @Slot(int)
    def request_channel_reset_cursor(self, channel_id: int) -> None:
        """UI «Сбросить курсор» — clears last_processed_msg_id."""
        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", channel_id=channel_id, action="reset_cursor")
            ok = await self._bot.reset_channel_cursor(channel_id)
            if not ok:
                return _err(
                    "Канал не найден.",
                    channel_id=channel_id,
                    action="reset_cursor",
                )
            return _ok({"channel_id": channel_id, "action": "reset_cursor"})

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="reset_cursor", channel_id=channel_id,
        )

    @Slot(int)
    def request_channel_delete(self, channel_id: int) -> None:
        """UI «Удалить канал» — nulls vacancy FKs, deletes row."""
        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", channel_id=channel_id, action="delete")
            detached = await self._bot.delete_channel(channel_id)
            if detached is None:
                return _err(
                    "Канал не найден.",
                    channel_id=channel_id,
                    action="delete",
                )
            return _ok({
                "channel_id": channel_id,
                "detached_vacancies": detached,
                "action": "delete",
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="delete", channel_id=channel_id,
        )

    @Slot(str)
    def request_create_channel(self, payload_json: str) -> None:
        """Add a new TelegramChannel from the UI «Добавить канал» modal.

        Accepts raw input — `@username`, plain `username`, or any t.me URL
        — and normalizes via the same parser used for HR contacts. On
        duplicate (channel already exists), returns ``ok=true`` with
        ``created=false`` so the UI selects the existing row instead of
        showing an error. Metadata fetch is opportunistic on the backend.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            raw = (payload.get("input") or "").strip()
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_create_channel", e)
            self.contacts_channel_action_done.emit(
                _err(f"Неверные поля: {e}", action="create")
            )
            return

        if not raw:
            self.contacts_channel_action_done.emit(
                _err("Укажите @username или ссылку на канал.", action="create")
            )
            return

        username = normalize_username(raw)
        if not username:
            self.contacts_channel_action_done.emit(
                _err(
                    "Не удалось распознать @username канала. "
                    "Поддерживаются форматы: @name, name, t.me/name.",
                    action="create",
                )
            )
            return

        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.", action="create")
            channel_id, status = await self._bot.add_channel(username)
            if status == "invalid":
                return _err(
                    f"Telegram не нашёл канал @{username}. Проверьте имя.",
                    action="create",
                    status=status,
                )
            return _ok({
                "channel_id": channel_id,
                "username": username,
                "created": status == "created",
                "action": "create",
                "status": status,
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(), action="create",
        )

    @Slot(str)
    def set_all_channels_active(self, payload_json: str) -> None:
        """Bulk-flip is_active на всех каналах. Echoes ``is_active`` чтобы
        фронт мог откатить optimistic-update на ошибке.
        """
        try:
            payload = json.loads(payload_json)
            is_active = bool(payload["is_active"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("set_all_channels_active", e)
            self.contacts_channel_action_done.emit(_err(
                f"Неверные поля: {e}", action="set_all_active",
            ))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    affected = await channels_repo.set_all_channels_active(
                        session, is_active
                    )
            return _ok({
                "is_active": is_active,
                "affected": affected,
                "action": "set_all_active",
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="set_all_active", is_active=is_active,
        )

    @Slot(str)
    def set_channel_active(self, payload_json: str) -> None:
        """Toggle TelegramChannel.is_active for one row.

        Echoes ``channel_id`` and the requested ``is_active`` so the UI can
        rollback its optimistic flip on error without re-querying the list.
        """
        # Парсим осторожно: если payload неполный, тянем сколько смогли,
        # чтобы action+channel_id всё же попали в _err — иначе фронт не
        # знает, какой именно ряд откатывать.
        channel_id = None
        is_active = None
        try:
            payload = json.loads(payload_json)
            raw_id = payload.get("channel_id")
            if raw_id is not None:
                channel_id = int(raw_id)
            raw_active = payload.get("is_active")
            if raw_active is not None:
                is_active = bool(raw_active)
            if channel_id is None or is_active is None:
                raise KeyError("channel_id / is_active")
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("set_channel_active", e)
            self.contacts_channel_action_done.emit(_err(
                f"Неверные поля: {e}",
                action="set_active",
                channel_id=channel_id,
                is_active=is_active,
            ))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                async with session.begin():
                    # Включить канал, который сейчас в blacklist'е, нельзя —
                    # блокируем на уровне бэка, чтобы любой канал-toggle (в
                    # т.ч. через bulk «Включить все») не оживлял запрещённое.
                    if is_active and await channels_repo.is_channel_blacklisted(
                        session, channel_id
                    ):
                        return _err(
                            "Канал в blacklist — нельзя включить.",
                            channel_id=channel_id,
                            is_active=is_active,
                            action="set_active",
                        )
                    ok = await channels_repo.set_channel_active(
                        session, channel_id, is_active
                    )
            if not ok:
                return _err(
                    "Канал не найден.",
                    channel_id=channel_id,
                    is_active=is_active,
                    action="set_active",
                )
            return _ok({
                "channel_id": channel_id,
                "is_active": is_active,
                "action": "set_active",
            })

        self._dispatch_action(
            self.contacts_channel_action_done, run(),
            action="set_active",
            channel_id=channel_id,
            is_active=is_active,
        )
