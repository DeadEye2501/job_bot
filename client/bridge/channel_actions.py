"""Что окно делает с каналом: опрос, курсор, чёрный список, состав."""

from __future__ import annotations

from backend.domain.telegram_identity import normalize_username
from backend.repository import channels as channels_repo
from client.bridge.answer import Denied, denied, launched, read_toggle, reply
from client.bridge.mark import CHANNEL_MARK, marked, unmarked
from client.bridge.refusals import (
    BLACKLISTED_STAYS_OFF,
    NO_BOT,
    NO_CHANNEL,
    POLL_REFUSALS,
)
from client.bridge.source_switch import switch_all


class ChannelActions:
    """Правки над каналом — всё, чем окно его трогает, а не показывает.

    Собирающий обязан держать `_hub`: из него берутся мотор, сессии, бот и
    очередь событий.

    Заслон и его снятие кладут в очередь весть о том, что списки контактов
    устарели: отметка отсева запечена в строках людей, компаний и каналов.
    Весть о самих каналах живёт не здесь — каналы меняются и сами по себе,
    когда сбор находит новый, и рассказывает об этом бот.
    """

    def block(self, channel_id: int) -> dict:
        """Занести канал в чёрный список.

        Написание — `@{username}`. Повторное нажатие второй записи не заводит:
        погашенная оживает, живая остаётся как есть. Канал при этом гаснет
        сразу — иначе он успел бы принести ещё объявлений, ровно от которых и
        ограждались.
        """

        return reply(self._hub.runner, marked(self._hub, CHANNEL_MARK, channel_id))

    def unblock(self, channel_id: int) -> dict:
        """Убрать канал из чёрного списка.

        Запись гасится, а не сносится: экран списка держит погашенные строки
        видимыми, с выключенным тумблером.
        """

        return reply(self._hub.runner, unmarked(self._hub, CHANNEL_MARK, channel_id))

    def poll_now(self, channel_id: int) -> dict:
        """Прогнать один канал вне очереди — кнопка «Прогнать сейчас».

        Ответ говорит только «пущено»: на каждый новый пост канала уходит до
        пяти обращений к модели, и ждать их значит держать зов вместе с окном.
        Чем кончилось, человек узнаёт вестью.
        """
        bot = self._hub.bot
        if bot is None:
            return denied(NO_BOT, channel_id=channel_id, action="poll_now")

        return launched(
            self._hub,
            lambda: bot.poll_channel_now(channel_id),
            POLL_REFUSALS,
            "Канал прогнан.",
            channel_id=channel_id,
            action="poll_now",
        )

    def reset_cursor(self, channel_id: int) -> dict:
        """Отмотать отметку прочитанного: канал перечитают с начала.

        Единственный способ вернуть пропущенные объявления — насколько хватает
        глубины добора (`backfill_limit`): дальше неё не смотрит и обход.

        Идёт мимо бота нарочно: это одна правка строки в базе, и запирать её на
        поднятого бота значило бы отказывать до входа в Telegram там, где
        Telegram не нужен вовсе.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    reset = await channels_repo.reset_channel_cursor(
                        session, channel_id
                    )
            if not reset:
                raise Denied(NO_CHANNEL, channel_id=channel_id, action="reset_cursor")
            return {"channel_id": channel_id, "action": "reset_cursor"}

        return reply(self._hub.runner, run())

    def delete(self, channel_id: int) -> dict:
        """Убрать канал.

        Вакансии при этом остаются, но теряют ссылку на источник. Сколько их,
        ответом не едет: окно этого числа не читает — оно видно строкой перечня
        каналов, из которой карточку и открывают.

        Идёт мимо бота нарочно, как и отмотка курсора выше: это одна правка
        строки в базе — сам бот только открывал сессию и звал тот же
        репозиторий, — и запирать её на поднятого бота значило бы отказывать до
        входа в Telegram там, где Telegram не нужен вовсе. Список каналов как
        раз и разбирают на ненастроенном приложении.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    detached = await channels_repo.delete_channel(
                        session, channel_id
                    )
            if detached is None:
                raise Denied(NO_CHANNEL, channel_id=channel_id, action="delete")
            return {"channel_id": channel_id, "action": "delete"}

        return reply(self._hub.runner, run())

    def create(self, payload: dict | None = None) -> dict:
        """Завести канал из окна «Добавить канал».

        Имя приходит как попало — `@name`, голое `name`, любой адрес `t.me` — и
        сводится к одному написанию тем же разбором, что и ник человека. Уже
        заведённый канал отказом не считается: ответ говорит `created: false`,
        и окно открывает готовую карточку вместо жалобы.
        """
        payload = payload if isinstance(payload, dict) else {}
        raw = (payload.get("input") or "").strip()
        if not raw:
            return denied("Укажите @username или ссылку на канал.", action="create")

        username = normalize_username(raw)
        if not username:
            return denied(
                "Не удалось распознать @username канала. "
                "Поддерживаются форматы: @name, name, t.me/name.",
                action="create",
            )

        async def run() -> dict:
            bot = self._hub.bot
            if bot is None:
                raise Denied(NO_BOT, action="create")
            channel_id, status = await bot.add_channel(username)
            if status == "invalid":
                raise Denied(
                    f"Telegram не нашёл канал @{username}. Проверьте имя.",
                    action="create", status=status,
                )
            if status == "error":
                raise Denied(
                    f"Не вышло спросить Telegram о канале @{username}. "
                    "Попробуйте ещё раз, причина в журнале.",
                    action="create", status=status,
                )
            return {
                "channel_id": channel_id,
                "username": username,
                "created": status == "created",
                "action": "create",
                "status": status,
            }

        return reply(self._hub.runner, run())

    def set_active(self, payload: dict) -> dict:
        """Включить или выключить один канал.

        Номер и признак возвращаются эхом: по ним окно откатывает тумблер,
        нажатый до ответа, не перечитывая перечень. Читаются они «сколько
        смогли» — прочитанная половина уезжает и в отказ, иначе окно не знало
        бы, какой именно тумблер возвращать на место.
        """
        channel_id, is_active, refusal = read_toggle(
            payload, "channel_id", "is_active", "channels.set_active"
        )
        if refusal is not None:
            return refusal

        return reply(self._hub.runner, self._switched(channel_id, is_active))

    async def _switched(self, channel_id: int, is_active: bool) -> dict:
        """Переключить один канал; запрет отсева держит репозиторий."""
        async with self._hub.session_factory() as session:
            async with session.begin():
                status = await channels_repo.set_channel_active(session, channel_id, is_active)
        if status != "ok":
            raise Denied(
                BLACKLISTED_STAYS_OFF if status == "blacklisted" else NO_CHANNEL,
                channel_id=channel_id, is_active=is_active, action="set_active",
            )
        return {
            "channel_id": channel_id,
            "is_active": is_active,
            "action": "set_active",
        }

    def set_all_active(self, payload: dict) -> dict:
        """Общий выключатель каналов; строки не трогает — см. `source_switch`."""
        return switch_all(self._hub, "channels_enabled", "channels.set_all_active", payload)
