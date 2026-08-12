"""Поля новых записей, прочитанные из нагрузки форм окна.

Мост держит слоты, сигналы и сессии; здесь — только перевод нагрузки формы
в поля записи. Отдельным модулем, потому что одна и та же форма открывается
с двух экранов: пока чтение жило в каждом слоте своё, копии расходились
молча, а мост уже за пределом строк и растить его нельзя.
"""

from backend.domain.telegram_identity import typed_username


def none_if_empty(value) -> str | None:
    """Пустое и пробельное — как отсутствие."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def read_new_company_fields(payload: dict) -> dict:
    """Поля новой компании из нагрузки формы «добавить компанию».

    Написания приходят с одного экрана строкой через запятую, с другого —
    готовым списком, и читаются оба: список, прочитанный как строка, лёг
    бы в колонку одним куском вида «['ООО Контур']», и ни одно написание
    не нашлось бы при сведении компаний.

    Название отдаётся строкой, а не отсутствием: слот отвечает на пустое
    «Название обязательно», и различать «не прислали» и «прислали пустое»
    ему незачем.
    """
    raw_aliases = payload.get("aliases")
    if isinstance(raw_aliases, str):
        raw_aliases = raw_aliases.split(",")
    elif not isinstance(raw_aliases, list):
        raw_aliases = []
    return {
        "name": none_if_empty(payload.get("name")) or "",
        "website": none_if_empty(payload.get("website")),
        "aliases": [
            spelling for spelling in (str(a).strip() for a in raw_aliases) if spelling
        ],
        "notes": none_if_empty(payload.get("notes")),
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
        "name": none_if_empty(payload.get("name")),
        "telegram_username": username,
        "telegram_user_id": None if raw_user_id in (None, "") else int(raw_user_id),
        "notes": none_if_empty(payload.get("notes")),
    }
