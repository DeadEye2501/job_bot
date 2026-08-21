"""Экран «Контакты / Каналы»: список каналов и их карточка."""

from __future__ import annotations

import logging

from backend.incoming import text_or_none
from backend.repository import channels as channels_repo, vacancies_mini
from client.bridge.answer import BAD_PAYLOAD, Denied, bad_fields, reply
from client.bridge.channel_actions import ChannelActions
from client.bridge.hub import Hub
from client.bridge.media import _avatar_data_url
from client.bridge.page import Page, read_page
from client.bridge.refusals import NO_CHANNEL
from client.bridge.wire import _channel_row_to_dict, _vacancy_mini_row_to_dict


logger = logging.getLogger(__name__)


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
                "channels": [_channel_row_to_dict(r) for r in rows],
            }

        return reply(self._hub.runner, run())

    def detail(self, channel_id: int) -> dict:
        """Карточка одного канала целиком, вместе с его числами.

        Номер едет обратно в отказе: по нему окно гасит строку, за которой
        канала уже нет, — перечень, из которого её открыли, мог устареть.
        Числа — разбивка по положениям дел и доли отклика, см. `ChannelStats`.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                detail = await channels_repo.get_channel_detail(session, channel_id)
            if detail is None:
                raise Denied(NO_CHANNEL, channel_id=channel_id)
            channel = detail.channel
            stats = detail.stats
            return {
                "channel_id": channel.id,
                "username": channel.username,
                "title": channel.title,
                "is_active": bool(channel.is_active),
                "avatar": _avatar_data_url(channel.avatar),
                "stats": {
                    "status_counts": stats.status_counts,
                    "total": stats.total,
                    "vacancies_per_day": stats.vacancies_per_day,
                    "fit_percent": stats.fit_percent,
                    "apply_percent": stats.apply_percent,
                    "response_percent": stats.response_percent,
                },
                "blacklist_value": detail.blacklist_value,
            }

        return reply(self._hub.runner, run())

    def vacancies(self, payload: dict) -> dict:
        """Страница вакансий этого канала — для его карточки.

        Нагрузка: `{channel_id, limit, offset}`. Дописать пришедшее или
        заменить показанное, окно решает само.
        """
        try:
            channel_id = int(payload["channel_id"])
            page = read_page(payload, default_limit=50)
        except BAD_PAYLOAD as e:
            return bad_fields("channels.vacancies", e)

        return reply(self._hub.runner, self._paged(channel_id, page))

    async def _paged(self, channel_id: int, page: Page) -> dict:
        """Страница вакансий канала и эхо того, о чём спрашивали."""
        async with self._hub.session_factory() as session:
            rows, has_more = await vacancies_mini.list_vacancies_for_channel(
                session, channel_id, limit=page.limit, offset=page.offset,
            )
            # Жалоба на живую беду: пусто здесь при непустом счёте в карточке.
            # По одному пустому списку не видно, где она — в запросе перечня
            # или в эхе моста; ноль против N различает эти два места.
            if not rows:
                total = await vacancies_mini.count_vacancies_for_channel(
                    session, channel_id
                )
                if total > 0:
                    logger.warning(
                        "канал %d: перечень вакансий пуст, а строк с этим "
                        "источником %d (потолок=%d сдвиг=%d) — разойтись со "
                        "счётчиком карточки он не должен",
                        channel_id, total, page.limit, page.offset,
                    )
        return {
            "channel_id": channel_id,
            "has_more": has_more,
            "vacancies": [_vacancy_mini_row_to_dict(v) for v in rows],
        }
