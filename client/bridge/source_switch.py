"""Общий выключатель источников одного рода — каналов или агрегаторов.

Отдельный признак в настройках, а не правка строк: выключенный гасит общий
обход целиком, а тумблеры строк остаются как были, и включённый снова он
возвращает в обход ровно прежние источники. Ручной прогон одного источника и
вход его не спрашивают.
"""

from __future__ import annotations

from client.bridge.answer import BAD_PAYLOAD, bad_fields, reply
from client.bridge.hub import Hub


def switch_all(hub: Hub, key: str, where: str, payload: dict) -> dict:
    """Записать выключатель `key` из нагрузки `{is_active}`; признак едет эхом.

    По эху окно откатывает отметку, поставленную до ответа.
    """
    try:
        is_active = bool(payload["is_active"])
    except BAD_PAYLOAD as e:
        return bad_fields(where, e, action="set_all_active")

    async def run() -> dict:
        await hub.rs.set_app(key, "true" if is_active else "false")
        return {"is_active": is_active}

    return reply(hub.runner, run())
