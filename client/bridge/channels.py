"""Экран «Контакты / Каналы»: список каналов и их карточка."""

from __future__ import annotations

from backend.incoming import text_or_none
from backend.repository import channels as channels_repo
from client.bridge.answer import Denied, reply
from client.bridge.channel_actions import ChannelActions
from client.bridge.hub import Hub
from client.bridge.refusals import NO_CHANNEL
from client.bridge.source_page import CHANNEL, source_vacancies
from client.bridge.wire import _channel_card_to_dict, _channel_row_to_dict


class Channels(ChannelActions):
    """Канал как запись в контактах: найти и показать.

    Разрезано на два файла по ответственности: перечень и карточка здесь, всё,
    чем канал трогают, — у примеси рядом. Поверхность у них при этом одна: окно
    видит один канал, а не список отдельно от кнопок в его карточке, и примесь
    здесь — способ разложить эту поверхность по файлам, а не задел под вторую
    реализацию.
    """

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def list(self, payload: dict | None = None) -> dict:
        """Все каналы разом — без страниц: их мало.

        Обратно едет и сама строка поиска: по ней окно рисует поле, когда
        перечень открывают из другого места с уже набранным словом.
        """
        # Не-объект сводится к пустоте, а не роняет разбор: поиск — дело окна,
        # и испорченная нагрузка не должна отнимать у человека весь перечень.
        payload = payload if isinstance(payload, dict) else {}
        search = text_or_none(payload.get("search"))

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                # Само-лечение: гасим каналы, попавшие в отсев, но всё ещё
                # помеченные работающими, — так бывает от правок базы мимо окна.
                # Дело идемпотентное и держит правило «в отсеве значит
                # выключен»: иначе обход продолжал бы читать запрещённые.
                async with session.begin():
                    await channels_repo.deactivate_blacklisted_channels(session)
                rows = await channels_repo.list_telegram_channels(
                    session, search=search
                )
            return {
                "search": search or "",
                "enabled": self._hub.rs.channels_enabled,
                "channels": [_channel_row_to_dict(r) for r in rows],
            }

        return reply(self._hub.runner, run())

    def detail(self, channel_id: int) -> dict:
        """Карточка одного канала целиком, вместе с его числами.

        Номер едет обратно в отказе: по нему окно гасит строку, за которой
        канала уже нет, — перечень, из которого её открыли, мог устареть.
        Числа — разбивка по положениям дел и доли отклика, см. `SourceStats`.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                detail = await channels_repo.get_channel_detail(session, channel_id)
            if detail is None:
                raise Denied(NO_CHANNEL, channel_id=channel_id)
            return _channel_card_to_dict(detail)

        return reply(self._hub.runner, run())

    def vacancies(self, payload: dict) -> dict:
        """Страница вакансий этого канала — для его карточки; см. `source_page`."""
        return source_vacancies(self._hub, CHANNEL, payload)
