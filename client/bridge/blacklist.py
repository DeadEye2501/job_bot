"""Экран «Контакты / Чёрный список»: чем окно правит отсев."""

from __future__ import annotations

from backend.models import BLACKLIST_KINDS
from backend.repository import blacklist as blacklist_repo, blacklist_candidates
from client.bridge.answer import Denied, bad_fields, denied, reply
from client.bridge.hub import Hub
from client.bridge.refusals import NO_ENTRY
from client.bridge.wire import _blacklist_row_to_dict
from client.bridge.form_payloads import read_toggle


class Blacklist:
    """Запись отсева: показать, завести, поправить, погасить, убрать."""

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def list(self) -> dict:
        """Все строки отсева разом — без страниц и отбора на стороне базы.

        Их мало, и окно отбирает у себя: по роду и по строке поиска.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows = await blacklist_repo.list_blacklist(session)
            return {"items": [_blacklist_row_to_dict(r) for r in rows]}

        return reply(self._hub.runner, run())

    def candidates(self, kind: str) -> dict:
        """Подсказки к форме заведения. Род возвращается эхом.

        Без эха окно не отличит ответ на свой вопрос от опоздавшего: род
        успевают сменить, пока летит первый.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                items = await blacklist_candidates.list_blacklist_candidates(
                    session, kind
                )
            return {"kind": kind, "items": items}

        return reply(self._hub.runner, run())

    def create(self, payload: dict | None = None) -> dict:
        """Завести строку отсева.

        Строку с тем же родом и значением база не задваивает: погашенную
        зажигает заново, живую отдаёт как есть. Отличить это окну даёт поле
        `created`.

        Пустое значение отбивает сам репозиторий, и слова у отказа его: своя
        проверка здесь была третьей копией одного текста, а срабатывала бы
        первой — разойдись они, человек читал бы на одном экране два разных
        отказа об одном.
        """
        payload = payload if isinstance(payload, dict) else {}
        kind = (payload.get("kind") or "").strip()
        value = (payload.get("value") or "").strip()
        reason = payload.get("reason")

        if kind not in BLACKLIST_KINDS:
            return denied("Неверный тип записи.", action="create")

        async def run() -> dict:
            try:
                async with self._hub.session_factory() as session:
                    async with session.begin():
                        row, outcome = await blacklist_repo.create_blacklist(
                            session, kind=kind, value=value, reason=reason,
                        )
                        new_id = row.id
            except blacklist_repo.BlacklistUpdateError as e:
                raise Denied(str(e), action="create")
            # Заведённая строка меняет отметку отсева у людей, компаний и
            # каналов — их списки надо перечитать целиком.
            self._hub.events.add("contacts_lists_changed")
            return {"id": new_id, "created": outcome == "created", "action": "create"}

        return reply(self._hub.runner, run())

    def update(self, payload: dict) -> dict:
        """Правка значения или причины у одной строки.

        Присылается только изменённое поле: отсутствующее база не трогает.
        """
        blacklist_id = None
        try:
            blacklist_id = int(payload["id"])
            fields = {
                name: payload.get(name)
                for name in ("value", "reason")
                if name in payload
            }
            if not fields:
                raise KeyError("value / reason")
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("blacklist.update", e, action="update", id=blacklist_id)

        async def run() -> dict:
            try:
                async with self._hub.session_factory() as session:
                    async with session.begin():
                        changed = await blacklist_repo.update_blacklist(
                            session, blacklist_id, **fields
                        )
            except blacklist_repo.BlacklistUpdateError as e:
                raise Denied(str(e), id=blacklist_id, action="update")
            if not changed:
                raise Denied(NO_ENTRY, id=blacklist_id, action="update")
            # Сменившееся значение перестаёт (или начинает) совпадать с отметкой
            # отсева у человека и компании — списки перечитываются.
            if "value" in fields:
                self._hub.events.add("contacts_lists_changed")
            return {"id": blacklist_id, "fields": list(fields), "action": "update"}

        return reply(self._hub.runner, run())

    def delete(self, blacklist_id: int) -> dict:
        """Убрать строку отсева. Спрашивает подтверждение окно, а не мост."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    gone = await blacklist_repo.delete_blacklist(session, blacklist_id)
            if not gone:
                raise Denied(NO_ENTRY, id=blacklist_id, action="delete")
            # Отметка отсева запечена в строках людей и компаний: не перечитав
            # их, окно показывало бы убранную запись как всё ещё запрещающую.
            self._hub.events.add("contacts_lists_changed")
            return {"id": blacklist_id, "action": "delete"}

        return reply(self._hub.runner, run())

    def set_active(self, payload: dict) -> dict:
        """Погасить или зажечь строку. Номер и признак возвращаются эхом.

        По ним окно откатывает отметку, поставленную до ответа.
        """
        blacklist_id = None
        active = None
        try:
            blacklist_id, active = read_toggle(payload, "id", "active")
            if blacklist_id is None or active is None:
                raise KeyError("id / active")
        # `AttributeError` ловится вместе с остальными: чтение нагрузки идёт
        # через помощника, и не-объект спотыкается уже внутри него — а беда
        # синхронная, до мотора, и мимо конверта ушла бы прямо в канал.
        except (AttributeError, ValueError, TypeError, KeyError) as e:
            return bad_fields(
                "set_active", e, action="set_active", id=blacklist_id, active=active
            )

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    switched = await blacklist_repo.set_blacklist_active(
                        session, blacklist_id, active
                    )
            if not switched:
                raise Denied(
                    NO_ENTRY, id=blacklist_id, active=active, action="set_active"
                )
            self._hub.events.add("contacts_lists_changed")
            return {"id": blacklist_id, "active": active, "action": "set_active"}

        return reply(self._hub.runner, run())
