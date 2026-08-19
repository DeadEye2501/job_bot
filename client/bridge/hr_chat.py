"""Переписка с человеком: страница сообщений, отправка, прочтение."""

from __future__ import annotations

import webview

from backend.bot.chat import EMPTY_MESSAGE
from backend.incoming import int_or_none, moment_or_none
from backend.repository import messages as messages_repo
from client.bridge.answer import Denied, bad_fields, denied, reply
from client.bridge.page import read_mode
from client.bridge.refusals import NO_BOT
from client.bridge.wire import _message_row_to_dict


class HrChat:
    """Что окно спрашивает и шлёт в переписке с одним человеком.

    Собирающий обязан держать `_hub`: из него берутся мотор, сессии и бот.

    Двух событий переписки — пришедшего письма и чужой отметки о прочтении —
    здесь нет: никто их не спрашивает, испускает их бот, и дом у них общий со
    всем, что случается само, — очередь событий (`lifespan`).
    """

    def messages(self, payload: dict) -> dict:
        """Страница переписки с одним человеком.

        Нагрузка: `{"hr_id": int, "before_id"?: int, "mode"?: "tail"|"older"}`.
        Умолчание — «свежие», полсотни последних. «older» просит следующие
        полсотни от самого старого показанного, чтобы окно дописало их сверху.
        """
        try:
            hr_id = int(payload["hr_id"])
            before_id = payload.get("before_id")
            mode = read_mode(payload, ("tail", "older"))
            epoch = int_or_none(payload.get("epoch"))
            if before_id is not None:
                before_id = int(before_id)
            before_sent_at = moment_or_none(payload.get("before_sent_at"))
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("messages", e)

        asked = {"hr_id": hr_id, "mode": mode, "epoch": epoch, "before_id": before_id}
        return reply(self._hub.runner, self._paged(asked, before_sent_at))

    async def _paged(self, asked: dict, before_sent_at) -> dict:
        """Полсотни писем и эхо того, о чём спрашивали.

        Эхо едет одним словарём: окно сверяет по нему, свой ли ответ пришёл, и
        разбирать его на четыре довода было бы только длиннее.
        """
        async with self._hub.session_factory() as session:
            msgs, has_more = await messages_repo.list_messages_for_hr(
                session, asked["hr_id"], limit=50,
                before_id=asked["before_id"],
                before_sent_at=before_sent_at,
            )
        return {
            **asked,
            "has_more": has_more,
            "messages": [_message_row_to_dict(m) for m in msgs],
        }

    def mark_read(self, hr_id: int) -> dict:
        """Пометить прочитанными все входящие письма человека.

        Идёт через `Bot.mark_hr_chat_read`, чтобы отметка уехала и в Telegram:
        собеседник должен увидеть, что письмо прочитано.
        """

        async def run() -> dict:
            bot = self._hub.bot
            if bot is None:
                raise Denied(NO_BOT, hr_id=hr_id)
            updated = await bot.mark_hr_chat_read(hr_id)
            # Самый частый способ, каким счётчик непрочитанного уменьшается:
            # не сказав об этом, окно держало бы вчерашнее число до
            # перезапуска.
            self._hub.events.add("unread_changed")
            return {"action": "mark_read", "hr_id": hr_id, "updated": updated}

        return reply(self._hub.runner, run())

    def send_message(self, payload: dict) -> dict:
        """Отправить человеку письмо.

        Идёт через `Bot.send_to_hr_chat`: шлёт тот же клиент Telegram, который
        опрашивает и собирает, — второго входа и второй сессии не заводится.
        Номер записи едет ответом, чтобы окно нашло только что появившийся
        пузырь, не перечитывая переписку целиком.
        """
        try:
            hr_id = int(payload["hr_id"])
            text = str(payload.get("text") or "").strip()
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("send_message", e)

        if not text:
            return denied(EMPTY_MESSAGE, hr_id=hr_id)

        async def run() -> dict:
            bot = self._hub.bot
            if bot is None:
                raise Denied(NO_BOT, hr_id=hr_id)
            try:
                msg = await bot.send_to_hr_chat(hr_id, text)
            except RuntimeError as e:
                raise Denied(str(e), hr_id=hr_id, action="send_message")
            return {"action": "send_message", "hr_id": hr_id, "message_id": msg.id}

        return reply(self._hub.runner, run())

    def pick_media(self, hr_id: int) -> dict:
        """Спросить у человека файл и отправить его этому собеседнику.

        Диалог у окна, а не у страницы, и дотянуться до него со страницы
        нельзя: браузер отдаёт выбранный файл содержимым, а не путём, —
        нарочно, — а боту нужен именно путь, чтобы приложить файл с диска.

        Этим же диалогом стоит и заслон: путь снова называет человек, а не
        страница, и до бота не доедет то, чего в диалоге не выбирали. Затем
        отправка и закрыта именем — поверхность моста собирается обходом полей,
        и открытый метод страница позвала бы с любым путём.

        Закрытый диалог отказом не считается: ничего не сломалось, человек
        передумал. Отзовись мост отказом, окно показало бы красную плашку на
        обычное «нет, не сейчас».
        """
        chosen = self._hub.window.create_file_dialog(webview.OPEN_DIALOG)
        if not chosen:
            return {"ok": {"cancelled": True}}
        return self._send_media({"hr_id": hr_id, "path": chosen[0]})

    def _send_media(self, payload: dict) -> dict:
        """Отправить человеку файл, названный диалогом окна.

        Путь приходит нагрузкой: диалог выбора держит окно, а мост шлёт уже
        названное. Снимком уйдёт файл или вложением, решает бот по расширению
        (`bot.chat.send_to_hr_media`) — окну эта разница не видна.
        """
        try:
            hr_id = int(payload["hr_id"])
            path = str(payload["path"])
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("send_media", e)

        async def run() -> dict:
            bot = self._hub.bot
            if bot is None:
                raise Denied(NO_BOT, hr_id=hr_id)
            try:
                msg = await bot.send_to_hr_media(hr_id, path)
            except RuntimeError as e:
                raise Denied(str(e), hr_id=hr_id, action="send_media")
            return {"action": "send_media", "hr_id": hr_id, "message_id": msg.id}

        return reply(self._hub.runner, run())
