"""Переписка с человеком: страница сообщений, отправка, прочтение."""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QFileDialog

from backend.payloads import int_or_none, moment_or_none
from backend.repository import messages as messages_repo
from client.bridge.answer import _err, _ok
from client.bridge.media import _media_url
from client.bridge.page import read_mode
from client.bridge.payload import _log_invalid_payload
from client.bridge.wire import _iso


logger = logging.getLogger(__name__)


class HrChatSlots:
    """Что окно спрашивает и шлёт в переписке с одним человеком.

    Подмешивающий обязан держать `_bot`, `_session_factory`, `_parent_widget`
    и `_dispatch`, а сверх того — сигнал `contacts_hr_action_done` из
    `HrSlots` и `_kick_unread` из `WindowStateSlots`: отправка и прочтение
    отвечают окну тем же сигналом, что и остальные правки карточки человека, и
    тем же движением поправляют счётчик непрочитанного.

    Два сигнала объявлены здесь, а испускает их бот: `contacts_hr_messages_arrived`
    на входящем письме и `contacts_hr_read_receipt` на чужой отметке о
    прочтении. Никто их не просит — это события, а не ответы.
    """

    contacts_hr_messages_loaded = Signal(str)
    contacts_hr_messages_arrived = Signal(str)
    contacts_hr_read_receipt = Signal(str)

    @Slot(int)
    def contacts_mark_hr_read(self, hr_id: int) -> None:
        """Mark all unread incoming messages for an HR as read (slice 5b).

        Routes through ``Bot.mark_hr_chat_read`` so the read receipt also
        propagates to Telegram via Pyrogram. Re-emits the list+detail so
        the unread bubble + chip drop immediately.
        """
        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не запущен.", hr_id=hr_id)
            try:
                updated = await self._bot.mark_hr_chat_read(hr_id)
            except Exception as e:
                logger.exception("contacts_mark_hr_read failed")
                return _err(
                    f"{type(e).__name__}: {e}",
                    hr_id=hr_id,
                    action="mark_read",
                )
            if updated:
                self._kick_unread()
            return _ok({
                "action": "mark_read",
                "hr_id": hr_id,
                "updated": updated,
            })

        self._dispatch(self.contacts_hr_action_done, run())

    @Slot(str)
    def contacts_send_hr_message(self, payload_json: str) -> None:
        """Send a chat message to an HR (slice 5a).

        Routes through ``Bot.send_to_hr_chat`` so the same Pyrogram client
        that polls and ingests is the one that sends — no second auth, no
        second session. On success, replays the messages query so JS sees
        the new outgoing bubble immediately.
        """
        try:
            payload = json.loads(payload_json)
            hr_id = int(payload["hr_id"])
            text = str(payload.get("text") or "").strip()
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("contacts_send_hr_message", e)
            self.contacts_hr_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        if not text:
            self.contacts_hr_action_done.emit(
                _err("Пустое сообщение.", hr_id=hr_id)
            )
            return

        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не запущен.", hr_id=hr_id)
            try:
                msg = await self._bot.send_to_hr_chat(hr_id, text)
            except RuntimeError as e:
                return _err(str(e), hr_id=hr_id, action="send_message")
            except Exception as e:
                logger.exception("contacts_send_hr_message failed")
                return _err(
                    f"{type(e).__name__}: {e}",
                    hr_id=hr_id,
                    action="send_message",
                )
            return _ok({
                "action": "send_message",
                "hr_id": hr_id,
                "message_id": msg.id,
            })

        self._dispatch(self.contacts_hr_action_done, run())

    @Slot(int)
    def contacts_pick_and_send_hr_media(self, hr_id: int) -> None:
        """Open native file picker, then ship the chosen file to the HR.

        Photo extensions go through ``send_photo``; everything else is sent
        as a document. Picker runs synchronously on the Qt thread; the
        actual upload is dispatched to the bot's async runner so the UI
        stays responsive during the Telegram round-trip.
        """
        path, _ = QFileDialog.getOpenFileName(
            self._parent_widget,
            "Прикрепить файл",
            "",
            "Все файлы (*);;Изображения (*.png *.jpg *.jpeg *.webp *.gif);;Документы (*.pdf *.doc *.docx *.txt *.zip *.rar *.7z)",
        )
        if not path:
            return

        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не запущен.", hr_id=hr_id)
            try:
                msg = await self._bot.send_to_hr_media(hr_id, path)
            except RuntimeError as e:
                return _err(str(e), hr_id=hr_id, action="send_media")
            except Exception as e:
                logger.exception("contacts_pick_and_send_hr_media failed")
                return _err(
                    f"{type(e).__name__}: {e}",
                    hr_id=hr_id,
                    action="send_media",
                )
            return _ok({
                "action": "send_media",
                "hr_id": hr_id,
                "message_id": msg.id,
            })

        self._dispatch(self.contacts_hr_action_done, run())

    @Slot(str)
    def request_contacts_hr_messages(self, payload_json: str) -> None:
        """Push a page of chat messages for the HR detail pane.

        Payload: ``{"hr_id": int, "before_id"?: int, "mode"?: "tail"|"older"}``.
        Default mode is "tail" — newest 50 messages. ``mode="older"`` requires
        ``before_id`` (oldest currently-loaded message id) and returns the
        next 50 older messages so JS can prepend them.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            hr_id = int(payload["hr_id"])
            before_id = payload.get("before_id")
            mode = read_mode(payload, ("tail", "older"))
            epoch = int_or_none(payload.get("epoch"))
            if before_id is not None:
                before_id = int(before_id)
            before_sent_at = moment_or_none(payload.get("before_sent_at"))
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_hr_messages", e)
            self.contacts_hr_messages_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                msgs, has_more = await messages_repo.list_messages_for_hr(
                    session, hr_id, limit=50,
                    before_id=before_id,
                    before_sent_at=before_sent_at,
                )
            return _ok({
                "hr_id": hr_id,
                "mode": mode,
                "epoch": epoch,
                "before_id": before_id,
                "has_more": has_more,
                "messages": [
                    {
                        "id": m.id,
                        "tg_message_id": m.tg_message_id,
                        "is_incoming": m.is_incoming,
                        "text": m.text,
                        "sent_at": _iso(m.sent_at),
                        "read_at": _iso(m.read_at),
                        "vacancy_id": m.vacancy_id,
                        "is_edited": m.is_edited,
                        "is_deleted": m.is_deleted,
                        "media_kind": m.media_kind,
                        "media_path": _media_url(m.media_path),
                        "media_name": m.media_name,
                    }
                    for m in msgs
                ],
            })

        self._dispatch(self.contacts_hr_messages_loaded, run())
