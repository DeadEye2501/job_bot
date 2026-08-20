"""Экран «Контакты / HR»: список людей, их карточка и правки в ней."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from backend.repository import hr_card, hr_identify, vacancies_mini
from client.bridge.answer import Denied, denied, reply
from client.bridge.cards import (
    CardSubject,
    asked_update,
    create_card,
    delete_card,
    listed,
    merge_candidates,
    merge_into,
    vacancies_of,
)
from client.bridge.hr_chat import HrChat
from client.bridge.hub import Hub
from client.bridge.mark import HR_MARK, marked, unmarked
from client.bridge.media import _avatar_data_url
from client.bridge.pickers import HR_PICKER
from client.bridge.refusals import (
    HR_TELEGRAM_TAKEN,
    IDENTITY_REQUIRED,
    NOTHING_TO_UPDATE,
    NO_HR,
)
from client.bridge.form_payloads import hr_is_identified, read_new_hr_fields


async def create_hr_row(session, fields: dict, **echo) -> int:
    """Завести человека по прочитанной форме окна и назвать его номер.

    Форма одна, а окон два: «Добавить HR» в контактах и заведение на ходу из
    подборщика при вакансии. Заслон у них общий: карточка без имени, без ника и
    без номера учётной записи не отличима от любой другой — в следующий раз
    человек завёл бы вторую такую же вместо того, чтобы найти эту.

    Занятый номер учётной записи объясняется словами, а не отказом базы: тот
    говорит про нарушенное ограничение таблицы, а человеку надо знать, что
    карточка этого собеседника уже есть — её завёл бот, а ищут её по имени.
    Соседний файл-близнец такой же случай объясняет так же.

    Поля отказа отдаёт зовущий: подборщику нужен номер вакансии, из которой
    заводят, окну контактов — ничего.
    """
    if not hr_is_identified(fields):
        raise Denied(IDENTITY_REQUIRED, **echo)
    try:
        async with session.begin():
            return (await hr_identify.create_hr(session, **fields)).id
    except IntegrityError:
        raise Denied(HR_TELEGRAM_TAKEN, **echo)


HR_CARD = CardSubject(
    picker=HR_PICKER,
    id_key="hr_id",
    missing=NO_HR,
    domain="hr",
    page_limit=None,
    listing={"sort_by": "last_activity"},
    read_fields=read_new_hr_fields,
    update_fields=("name", "telegram_username", "notes"),
    mini_vacancies=vacancies_mini.list_vacancies_for_hr,
    merge_row=hr_card.merge_hr,
    delete_row=hr_card.delete_hr,
    create_row=create_hr_row,
    merge_action="merge_hr",
    delete_action="delete_hr",
    create_action="create_hr",
    news=("contacts_lists_changed", "unread_changed"),
)
"""Человек, каким его знает общая карточка контакта.

Счёт непрочитанного среди вестей потому, что переписку сносят и переносят
вместе с ним; у компании переписки нет вовсе.
"""


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
        страницами: потолок и сдвиг читаются как у списка вакансий.
        """
        return listed(self._hub, HR_CARD, payload)

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
                "last_company_id": detail.last_company_id,
                "last_company_name": detail.last_company_name,
                "unread_count": detail.unread_count,
                "blacklist_value": detail.blacklist_value,
                "avatar": _avatar_data_url(detail.hr.avatar),
            }

        return reply(self._hub.runner, run())

    def vacancies(self, payload: dict) -> dict:
        """Короткий список вакансий этого человека — для его карточки.

        Нагрузка: `{hr_id}`.
        """
        return vacancies_of(self._hub, HR_CARD, payload)

    def merge_picker(self, payload: dict) -> dict:
        """Кандидаты, в которых можно влить эту карточку.

        Строка та же, что у подборщика вакансий, за вычетом самой
        поглощаемой карточки.
        """
        return merge_candidates(self._hub, HR_CARD, payload)

    def merge(self, payload: dict) -> dict:
        """Влить поглощаемую карточку в оставшуюся.

        Вакансии переезжают на оставшегося, поглощённая строка сносится; дело
        делает `hr_card.merge_hr`.

        Переписка переезжает не всегда: она ходит вместе с учётной записью
        Telegram, и если своя у выжившего уже есть — чужую переписку **стирают**
        (`hr_card._move_or_drop_chat`). Окно про это говорит человеку прямо,
        перед нажатием.
        """
        return merge_into(self._hub, HR_CARD, payload)

    def delete(self, hr_id: int) -> dict:
        """Снести карточку человека вместе с перепиской (`hr_card.delete_hr`)."""
        return delete_card(self._hub, HR_CARD, hr_id)

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

        return reply(self._hub.runner, marked(self._hub, HR_MARK, hr_id))

    def unblock(self, hr_id: int) -> dict:
        """Убрать человека из чёрного списка.

        Запись гасится, а не сносится: экран списка держит погашенные строки
        видимыми, с выключенным тумблером, — этого от кнопки «убрать» здесь и
        ждут.
        """

        return reply(self._hub.runner, unmarked(self._hub, HR_MARK, hr_id))

    def update(self, payload: dict) -> dict:
        """Поправить одно или несколько полей карточки.

        Нагрузка: `{"hr_id": int, "name"?: str, "telegram_username"?: str,
        "notes"?: str}`. Пропущенный ключ значит «не трогать» — часового
        держит репозиторий; пустая строка сводится к пустоте.

        Ответ называет поправленные поля: окно перечитывает по нему карточку
        и берёт из неё приведённые написания — например, ник без «@».
        """
        hr_id, kwargs, refused = asked_update(payload, HR_CARD)
        if refused is not None:
            return refused
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
        return create_card(self._hub, HR_CARD, payload)
