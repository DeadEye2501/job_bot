"""Переписка с человеком: страница сообщений, отправка, прочтение."""

from __future__ import annotations

import logging

from backend.bot.chat import EMPTY_MESSAGE
from backend.incoming import moment_or_none
from backend.repository import messages as messages_repo
from client.bridge.answer import BAD_PAYLOAD, Denied, bad_fields, denied, reply
from client.bridge.desktop import chosen_path, closed_dialog
from client.bridge.page import read_page
from client.bridge.refusals import NO_BOT, SEND_BROKE
from client.bridge.wire import _message_row_to_dict


logger = logging.getLogger(__name__)


class HrChat:
    """Что окно спрашивает и шлёт в переписке с одним человеком.

    Собирающий обязан держать `_hub`: из него берутся мотор, сессии и бот.

    Двух событий переписки — пришедшего письма и чужой отметки о прочтении —
    здесь нет: никто их не спрашивает, испускает их бот, и дом у них общий со
    всем, что случается само, — очередь событий (`lifespan`).
    """

    def messages(self, payload: dict) -> dict:
        """Страница переписки с одним человеком.

        Нагрузка: `{"hr_id": int, "limit"?: int, "before_sent_at"?, "before_id"?: int}`.
        Умолчание — «свежие», полсотни последних; отсечка просит следующие
        полсотни от самого старого показанного, чтобы окно дописало их сверху.

        Потолок читается тем же `read_page`, что и у прочих перечней, вместе с
        его границей: перечитывая хвост по вести о новом письме, окно просит не
        меньше показанного. Без этого пролиставший переписку к началу разговора
        терял дочитанное на каждом входящем — хвост приходил полусотней и
        ложился заменой.

        Отсечка — пара «время и номер», и слать надо обе половины: время у
        писем повторяется, а номера растут не в том же порядке (догон истории
        заводит старые письма позже). Одинокий номер не режет ничего, и
        страница вернётся та же самая; негодное время снимает отсечку целиком.
        """
        try:
            hr_id = int(payload["hr_id"])
            before_id = payload.get("before_id")
            if before_id is not None:
                before_id = int(before_id)
            before_sent_at = moment_or_none(payload.get("before_sent_at"))
        except BAD_PAYLOAD as e:
            return bad_fields("messages", e)

        limit = read_page(payload, default_limit=50).limit
        asked = {"hr_id": hr_id, "before_id": before_id}
        return reply(self._hub.runner, self._paged(asked, before_sent_at, limit))

    async def _paged(self, asked: dict, before_sent_at, limit: int) -> dict:
        """Страница писем и эхо того, о чём спрашивали.

        Эхо едет одним словарём, а не разобранным на доводы: разбирать его
        было бы только длиннее.
        """
        async with self._hub.session_factory() as session:
            msgs, has_more = await messages_repo.list_messages_for_hr(
                session, asked["hr_id"], limit=limit,
                before_id=asked["before_id"],
                before_sent_at=before_sent_at,
            )
        return {
            **asked,
            "has_more": has_more,
            "messages": [_message_row_to_dict(m) for m in msgs],
        }

    async def _sent(self, sending, hr_id: int, action: str) -> dict:
        """Отдать боту письмо или файл и назвать номер появившейся записи.

        Тело одно на обе кнопки: различаются они зовом бота и именем действия,
        а всё вокруг — заслон на неподнятого бота, разбор беды и форма ответа —
        у них общее.

        Бед две породы, и человеку они разные. `RuntimeError` — заслон самого
        бота: выключен, собеседник в отсеве, ника нет; слова у него свои, и по
        ним видно, где чинить. Всё прочее роняет зов Pyrogram — отказ Telegram
        и оборванная сеть, — и мимо перехвата это уезжало окну поломкой без
        единого внятного слова.
        """
        bot = self._hub.bot
        if bot is None:
            raise Denied(NO_BOT, hr_id=hr_id)
        try:
            msg = await sending(bot)
        except RuntimeError as e:
            # След остаётся и у отказа: внутренние `RuntimeError` из asyncio и
            # Pyrogram неотличимы здесь от заслона самого бота, и без записи
            # такая беда уехала бы человеку английской строкой без следа.
            logger.info("%s: бот отказал, hr=%s: %s", action, hr_id, e)
            raise Denied(str(e), hr_id=hr_id, action=action)
        except Exception:
            logger.exception("%s: отправка сорвалась, hr=%s", action, hr_id)
            raise Denied(SEND_BROKE, hr_id=hr_id, action=action)
        return {"action": action, "hr_id": hr_id, "message_id": msg.id}

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
        except BAD_PAYLOAD as e:
            return bad_fields("send_message", e)

        if not text:
            return denied(EMPTY_MESSAGE, hr_id=hr_id)

        return reply(
            self._hub.runner,
            self._sent(lambda bot: bot.send_to_hr_chat(hr_id, text), hr_id, "send_message"),
        )

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
        path = chosen_path(self._hub.window)
        if path is None:
            return closed_dialog()
        return self._send_media({"hr_id": hr_id, "path": path})

    def _send_media(self, payload: dict) -> dict:
        """Отправить человеку файл, названный диалогом окна.

        Путь приходит нагрузкой: диалог выбора держит окно, а мост шлёт уже
        названное. Снимком уйдёт файл или вложением, решает бот по расширению
        (`bot.chat.send_to_hr_media`) — окну эта разница не видна.
        """
        try:
            hr_id = int(payload["hr_id"])
            path = str(payload["path"])
        except BAD_PAYLOAD as e:
            return bad_fields("send_media", e)

        return reply(
            self._hub.runner,
            self._sent(lambda bot: bot.send_to_hr_media(hr_id, path), hr_id, "send_media"),
        )
