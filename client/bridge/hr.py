"""Экран «Контакты / HR»: список людей, их карточка и правки в ней."""

from __future__ import annotations

from backend.payloads import int_or_none, text_or_none
from backend.repository import (
    hr_card,
    hr_identify,
    hr_list,
    vacancies_mini,
)
from client.bridge.answer import Denied, bad_fields, denied, reply
from client.bridge.hr_chat import HrChat
from client.bridge.hub import Hub
from client.bridge.mark import HR_MARK, mark, unmark
from client.bridge.media import _avatar_data_url
from client.bridge.page import read_page
from client.bridge.pickers import HR_PICKER, merge_picker
from client.bridge.refusals import IDENTITY_REQUIRED, NOTHING_TO_UPDATE, NO_HR
from client.bridge.wire import _hr_picker_row_to_dict, _vacancy_mini_row_to_dict
from client.form_payloads import hr_is_identified, read_new_hr_fields


async def create_hr_row(session, fields: dict, **echo) -> int:
    """Завести человека по прочитанной форме окна и назвать его номер.

    Форма одна, а окон два: «Добавить HR» в контактах и заведение на ходу из
    подборщика при вакансии. Заслон у них общий: карточка без имени, без ника и
    без номера учётной записи не отличима от любой другой — в следующий раз
    человек завёл бы вторую такую же вместо того, чтобы найти эту.

    Поля отказа отдаёт зовущий: подборщику нужен номер вакансии, из которой
    заводят, окну контактов — ничего.
    """
    if not hr_is_identified(fields):
        raise Denied(IDENTITY_REQUIRED, **echo)
    async with session.begin():
        return (await hr_identify.create_hr(session, **fields)).id


class Hr(HrChat):
    """Человек как запись в контактах: найти, показать, поправить, убрать.

    Разрезано на два файла по ответственности: карточка и правки в ней здесь,
    переписка с тем же человеком — у примеси рядом. Поверхность у них при этом
    одна: окно видит одного человека, а не карточку отдельно от переписки, и
    примесь здесь — способ разложить эту поверхность по файлам, а не задел под
    вторую реализацию. Складывать её вложенным полем (`api.hr.chat.*`) значило
    бы завести домен, которого в плане нет.

    Слияние и снос кладут в очередь две вести — списки контактов и счётчик
    непрочитанного собраны из того же, — а заслон меняет только списки. Не
    сказав, окно осталось бы со вчерашними числами.
    """

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def list(self, payload: dict | None = None) -> dict:
        """Перечень людей с поиском и бесконечной прокруткой.

        Запрос под ним тот же, что у подборщика (`list_hr_with_counts`), но со
        страницами: потолок, сдвиг и режим читаются как у списка вакансий.
        Порядковый знак уезжает эхом — по нему окно отбрасывает ответ,
        устаревший, пока менялись поиск или порядок.
        """
        # Не-объект сводится к пустоте, а не роняет разбор: поиск — дело окна,
        # и испорченная нагрузка не должна отнимать у человека весь перечень.
        payload = payload if isinstance(payload, dict) else {}
        search = text_or_none(payload.get("search"))
        page = read_page(payload)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows, has_more = await hr_list.list_hr_with_counts(
                    session,
                    search=search,
                    limit=page.limit,
                    offset=page.offset,
                    sort_by="last_activity",
                )
            return {
                "search": search or "",
                "hrs": [_hr_picker_row_to_dict(r) for r in rows],
                "has_more": has_more,
                "mode": page.mode,
                "offset": page.offset,
                "epoch": page.epoch,
            }

        return reply(self._hub.runner, run())

    def detail(self, hr_id: int) -> dict:
        """Карточка одного человека целиком.

        Номер едет обратно в ответе: по нему окно отбрасывает ответ про
        строку, с которой человек уже ушёл, нажав соседнюю.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                detail = await hr_card.get_hr_detail(session, hr_id)
            if detail is None:
                raise Denied(NO_HR, hr_id=hr_id)
            return {
                "hr_id": detail.hr.id,
                "name": detail.hr.name,
                "telegram_username": detail.hr.telegram_username,
                "telegram_user_id": detail.hr.telegram_user_id,
                "notes": detail.hr.notes,
                "vacancy_count": detail.vacancy_count,
                "last_company_id": detail.last_company_id,
                "last_company_name": detail.last_company_name,
                "unread_count": detail.unread_count,
                "blacklist_value": detail.blacklist_value,
                "avatar": _avatar_data_url(detail.hr.avatar),
            }

        return reply(self._hub.runner, run())

    def vacancies(self, payload: dict) -> dict:
        """Короткий список вакансий этого человека — для его карточки.

        Нагрузка: `{hr_id, epoch}`. Номер отсеивает ответ про другого
        выбранного, порядковый знак — про того же самого, спрошенного дважды
        подряд (например, быстрым переключением статуса вакансии). Оба уезжают
        обратно эхом, устаревшее окно отбрасывает.
        """
        try:
            hr_id = int(payload["hr_id"])
            epoch = int_or_none(payload.get("epoch"))
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("hr.vacancies", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows = await vacancies_mini.list_vacancies_for_hr(session, hr_id)
            return {
                "hr_id": hr_id,
                "epoch": epoch,
                "vacancies": [_vacancy_mini_row_to_dict(v) for v in rows],
            }

        return reply(self._hub.runner, run())

    def merge_picker(self, payload: dict) -> dict:
        """Кандидаты, в которых можно влить эту карточку.

        Строка та же, что у подборщика вакансий, за вычетом самой
        поглощаемой карточки.
        """
        try:
            absorbed_id = int(payload["absorbed_id"])
            search = text_or_none(payload.get("search"))
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("hr.merge_picker", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                return await merge_picker(session, HR_PICKER, absorbed_id, search)

        return reply(self._hub.runner, run())

    def merge(self, payload: dict) -> dict:
        """Влить поглощаемую карточку в оставшуюся.

        Вакансии и переписка переезжают на оставшегося, поглощённая строка
        сносится; дело делает `hr_card.merge_hr`.
        """
        try:
            absorbed_id = int(payload["absorbed_id"])
            survivor_id = int(payload["survivor_id"])
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("hr.merge", e)

        async def run() -> dict:
            try:
                async with self._hub.session_factory() as session:
                    async with session.begin():
                        await hr_card.merge_hr(
                            session,
                            absorbed_id=absorbed_id,
                            survivor_id=survivor_id,
                        )
            except ValueError as e:
                raise Denied(str(e), absorbed_id=absorbed_id, action="merge_hr")
            self._hub.events.add("contacts_lists_changed")
            self._hub.events.add("unread_changed")
            return {
                "action": "merge_hr",
                "absorbed_id": absorbed_id,
                "survivor_id": survivor_id,
            }

        return reply(self._hub.runner, run())

    def delete(self, hr_id: int) -> dict:
        """Снести карточку человека вместе с перепиской (`hr_card.delete_hr`)."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                if not await hr_card.delete_hr(session, hr_id):
                    raise Denied(NO_HR, hr_id=hr_id, action="delete_hr")
                await session.commit()
            self._hub.events.add("contacts_lists_changed")
            self._hub.events.add("unread_changed")
            return {"action": "delete_hr", "hr_id": hr_id}

        return reply(self._hub.runner, run())

    def block(self, hr_id: int) -> dict:
        """Занести человека в чёрный список.

        Написание — `user_id:{id}`, если номер учётной записи есть, иначе
        `@{username}`: ник сменяемый, и отметка на нём слетела бы с первым же
        письмом.
        Повторное нажатие второй записи не заводит: погашенная оживает, живая
        остаётся как есть, — и различают эти два исхода два поля ответа.
        `existed` говорит только, что запись уже была; какой из двух случаев
        это был, говорит `was_inactive`, и карточка рисует их по-разному.
        Причина остаётся пустой — её дописывают на экране самого списка.
        Карточку это не сносит: снос — отдельная кнопка.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                marked = await mark(session, HR_MARK, hr_id)
            self._hub.events.add("contacts_lists_changed")
            return marked

        return reply(self._hub.runner, run())

    def unblock(self, hr_id: int) -> dict:
        """Убрать человека из чёрного списка.

        Запись гасится, а не сносится: экран списка держит погашенные строки
        видимыми, с выключенным тумблером, — этого от кнопки «убрать» здесь и
        ждут.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                unmarked = await unmark(session, HR_MARK, hr_id)
            self._hub.events.add("contacts_lists_changed")
            return unmarked

        return reply(self._hub.runner, run())

    def update(self, payload: dict) -> dict:
        """Поправить одно или несколько полей карточки.

        Нагрузка: `{"hr_id": int, "name"?: str, "telegram_username"?: str,
        "notes"?: str}`. Пропущенный ключ значит «не трогать» — часового
        держит репозиторий; пустая строка сводится к пустоте.

        Ответ называет поправленные поля: окно перечитывает по нему карточку
        и берёт из неё приведённые написания — например, ник без «@».
        """
        try:
            hr_id = int(payload["hr_id"])
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("hr.update", e)

        # Только присланные поля: отсутствие ключа значит «не трогать».
        kwargs = {
            key: payload[key]
            for key in ("name", "telegram_username", "notes")
            if key in payload
        }
        if not kwargs:
            return denied(NOTHING_TO_UPDATE, hr_id=hr_id)

        async def run() -> dict:
            try:
                async with self._hub.session_factory() as session:
                    async with session.begin():
                        ok = await hr_card.update_hr_fields(session, hr_id, **kwargs)
            except ValueError as e:  # негодный ник — ответ формы, а не сбой
                raise Denied(f"Неверные поля: {e}", hr_id=hr_id, action="update_hr")
            if not ok:
                raise Denied(NO_HR, hr_id=hr_id, action="update_hr")
            return {
                "action": "update_hr",
                "hr_id": hr_id,
                "fields": list(kwargs.keys()),
            }

        return reply(self._hub.runner, run())

    def create(self, payload: dict) -> dict:
        """Завести человека из окна «Добавить HR».

        Номер заведённого едет ответом, чтобы окно подсветило новую строку;
        перечень оно перечитывает следом само. Само заведение — общее с
        подборщиком при вакансии.
        """
        try:
            fields = read_new_hr_fields(payload)
        # `AttributeError` — про не-объект в нагрузке: помощник читает её
        # ключами, и спотыкается он до мотора, мимо конверта.
        except (AttributeError, ValueError, TypeError, KeyError) as e:
            return bad_fields("hr.create", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                created_id = await create_hr_row(session, fields)
            return {"action": "create_hr", "created_id": created_id}

        return reply(self._hub.runner, run())
