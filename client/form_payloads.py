"""Поля новых записей, прочитанные из нагрузки форм окна.

Мост держит слоты, сигналы и сессии; здесь — только перевод нагрузки формы
в поля записи. Отдельным модулем, потому что одна и та же форма открывается
с двух экранов: пока чтение жило в каждом слоте своё, копии расходились
молча, а мост уже за пределом строк и растить его нельзя.
"""

from backend.domain.telegram_identity import typed_username
from backend.payloads import text_or_none


def read_company_spellings(raw) -> list[str]:
    """Написания компании из нагрузки формы.

    Приходят с одного экрана строкой через запятую, с другого — готовым
    списком, и читаются оба: список, прочитанный как строка, лёг бы в
    колонку одним куском вида «['ООО Контур']», и ни одно написание не
    нашлось бы при сведении компаний. Пустые и пробельные выпадают: в
    списке они не значат ничего, а на экране выглядят пропавшей строкой.
    """
    if isinstance(raw, str):
        raw = raw.split(",")
    elif not isinstance(raw, list):
        raw = []
    return [
        spelling for spelling in (str(a).strip() for a in raw) if spelling
    ]


def read_new_company_fields(payload: dict) -> dict:
    """Поля новой компании из нагрузки формы «добавить компанию».

    Написания читает :func:`read_company_spellings` — их же читает правка
    карточки.

    Название отдаётся строкой, а не отсутствием: слот отвечает на пустое
    «Название обязательно», и различать «не прислали» и «прислали пустое»
    ему незачем.
    """
    return {
        "name": text_or_none(payload.get("name")) or "",
        "website": text_or_none(payload.get("website")),
        "aliases": read_company_spellings(payload.get("aliases")),
        "notes": text_or_none(payload.get("notes")),
    }


def hr_is_identified(fields: dict) -> bool:
    """Есть ли чем назвать HR: имя, ник или номер учётной записи.

    Заметки в счёт не идут: запись, у которой нет ни одного способа
    сослаться на человека, не найти ни поиском, ни отправкой — на экране
    она осталась бы строкой из одних заметок.
    """
    return any(
        fields[key] is not None
        for key in ("name", "telegram_username", "telegram_user_id")
    )


def read_new_hr_fields(payload: dict) -> dict:
    """Поля нового HR из нагрузки формы «добавить HR».

    Ник разбирается строго тем же объявлением, что и ник из объявления о
    работе: в колонку идёт голое написание, из которого кнопка «в чёрный
    список» строит `@{username}`, а отправка — адрес собеседника. Ссылку
    из шапки чата (`t.me/ivanov`) разбор понимает — ник чаще копируют ею,
    чем по буквам.

    Что телеграмовским ником не является — имя человека, номер телефона,
    чужая ссылка — роняет `ValueError`, а не ложится в колонку: молча
    записанное, оно нашлось бы только в тот миг, когда отправка не находит
    собеседника и не может сказать почему.

    Правка того же поля на карточке HR (`repository/hr_card.update_hr_fields`)
    разбирает ник тем же объявлением: форма правки не может принимать то,
    что форма заведения отвергает.

    Нечисловой номер учётной записи роняет `ValueError` по той же причине:
    молча положенный ноль привязал бы HR к чужой учётной записи. Оба броска
    ловит слот и отвечает окну «Неверные поля».
    """
    typed = payload.get("telegram_username")
    username = None if typed is None else typed_username(typed)
    raw_user_id = payload.get("telegram_user_id")
    return {
        "name": text_or_none(payload.get("name")),
        "telegram_username": username,
        "telegram_user_id": None if raw_user_id in (None, "") else int(raw_user_id),
        "notes": text_or_none(payload.get("notes")),
    }
