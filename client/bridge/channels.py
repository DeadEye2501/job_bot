"""Экран «Контакты / Каналы»: список каналов и их карточка."""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import Signal, Slot
from sqlalchemy import func, select

from backend.models import Vacancy
from backend.payloads import int_or_none, text_or_none
from backend.repository import channels as channels_repo, vacancies_mini
from client.bridge.answer import _err, _ok
from client.bridge.refusals import NO_CHANNEL
from client.bridge.media import _avatar_data_url
from client.bridge.page import read_page
from client.bridge.payload import _log_invalid_payload
from client.bridge.wire import _channel_row_to_dict, _iso


logger = logging.getLogger(__name__)


class ChannelSlots:
    """Канал как запись в контактах: найти и показать.

    Подмешивающий обязан держать `_session_factory` и `_dispatch`.
    """

    contacts_channel_list_loaded = Signal(str)
    contacts_channel_detail_loaded = Signal(str)
    contacts_channel_vacancies_loaded = Signal(str)

    @Slot(str)
    def request_contacts_channel_list(self, payload_json: str) -> None:
        """Full list of Telegram channels for the Contacts/Channels pane.

        No pagination — channel sets are tiny. Echoes the request epoch so
        the UI can drop stale responses when search races.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            search = text_or_none(payload.get("search"))
            epoch = int_or_none(payload.get("epoch"))
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_contacts_channel_list", e)
            self.contacts_channel_list_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                # Self-heal: тушим каналы, попавшие в blacklist, но всё ещё
                # помеченные is_active=true (исторический дрейф / правки БД
                # мимо UI). Идемпотентно, и держит инвариант «blacklisted
                # ⇒ is_active=false» — иначе bot polling всё ещё трогал бы
                # запрещённые каналы.
                async with session.begin():
                    await channels_repo.deactivate_blacklisted_channels(session)
                rows = await channels_repo.list_telegram_channels(session, search=search)
            return _ok({
                "search": search or "",
                "channels": [_channel_row_to_dict(r) for r in rows],
                "epoch": epoch,
            })

        self._dispatch(self.contacts_channel_list_loaded, run())

    @Slot(int)
    def request_contacts_channel_detail(self, channel_id: int) -> None:
        """Detail-pane payload for one Telegram channel.

        Echoes ``channel_id`` so the UI drops stale responses when the user
        clicks another row mid-flight.
        Includes computed stats (status breakdown + KPI ratios + recent
        ingestion rate) — see ``ChannelStats`` for shape.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                detail = await channels_repo.get_channel_detail(session, channel_id)
            if detail is None:
                return _err(NO_CHANNEL, channel_id=channel_id)
            ch = detail.channel
            stats = detail.stats
            return _ok({
                "channel_id": ch.id,
                "username": ch.username,
                "title": ch.title,
                "is_active": bool(ch.is_active),
                "avatar": _avatar_data_url(ch.avatar),
                "stats": {
                    "status_counts": stats.status_counts,
                    "total": stats.total,
                    "vacancies_per_day": stats.vacancies_per_day,
                    "fit_percent": stats.fit_percent,
                    "apply_percent": stats.apply_percent,
                    "response_percent": stats.response_percent,
                },
                "blacklist_value": detail.blacklist_value,
            })

        self._dispatch(self.contacts_channel_detail_loaded, run())

    @Slot(str)
    def request_contacts_channel_vacancies(self, payload_json: str) -> None:
        """Pagination-aware vacancies fetch for the channels detail pane.

        Payload: ``{channel_id, limit, offset, mode}``. ``mode`` ∈
        {"replace", "append"} — replace wipes JS-side list, append concat'ит
        к существующему. Backend echoes channel_id + offset + has_more
        чтобы фронт мог дропать stale-ответы при гонке скролла/выбора.
        """
        try:
            payload = json.loads(payload_json) if payload_json else {}
            channel_id = int(payload["channel_id"])
            page = read_page(payload, default_limit=50, modes=("replace", "append"))
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("request_contacts_channel_vacancies", e)
            self.contacts_channel_vacancies_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            async with self._session_factory() as session:
                rows, has_more = await vacancies_mini.list_vacancies_for_channel(
                    session, channel_id, limit=page.limit, offset=page.offset,
                )
                # Diagnostic — раз баг проявляется: 0 здесь vs N в stats
                # помогает понять, в репо ли проблема или в bridge-эхо.
                if not rows:
                    total_for_channel = int(
                        (
                            await session.execute(
                                select(func.count(Vacancy.id))
                                .where(Vacancy.source_channel_id == channel_id)
                            )
                        ).scalar_one()
                    )
                    if total_for_channel > 0:
                        logger.warning(
                            "channel %d: list_vacancies_for_channel returned 0 "
                            "but %d rows match source_channel_id (limit=%d offset=%d) "
                            "— investigate query mismatch with stats",
                            channel_id,
                            total_for_channel,
                            page.limit,
                            page.offset,
                        )
            return _ok({
                "channel_id": channel_id,
                "offset": page.offset,
                "mode": page.mode,
                "has_more": has_more,
                "vacancies": [
                    {
                        "id": v.id,
                        "title": v.title or "",
                        "status": v.status.value if v.status else "New",
                        "score": v.score,
                        "created_at": _iso(v.created_at),
                        "posted_at": _iso(v.posted_at),
                    }
                    for v in rows
                ],
            })

        self._dispatch(self.contacts_channel_vacancies_loaded, run())
