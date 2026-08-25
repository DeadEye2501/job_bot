"""Поля записи, прочитанные из нагрузки форм окна.

Слот моста держит сигналы и сессию; здесь — только перевод нагрузки формы в
поля записи: и целой новой, и одного признака у уже заведённой. Отдельным
модулем, потому что одна и та же форма открывается с двух экранов: пока чтение
жило в каждом слоте своё, копии расходились молча.

В самом пакете моста, а не рядом с ним: читают это только его слоты, и по
ответственности сосед у чтения один — `payload.py` с `choices.py`.
"""

from backend.domain.salary import currency_sign
from backend.domain.taxonomy import GRADES, WORK_FORMATS
from backend.domain.telegram_identity import typed_username
from backend.incoming import (
    int_or_none,
    moment_or_none,
    normalize_enum,
    str_list,
    text_or_none,
)


def read_toggle(
    payload: dict, id_key: str, flag_key: str
) -> tuple[int | None, bool | None]:
    """Номер строки и её новое положение из нагрузки тумблера.

    Оба поля обязательны, но читаются «сколько смогли»: негодное или
    пропущенное становится пустотой, а не роняет разбор. Прочитанную половину
    зовущий кладёт в отказ — окно по ней возвращает на место тот тумблер,
    который человек нажал, и не трогает соседние.

    Признак читается как есть: окно шлёт его булевым, а всё, что доедет иным,
    значит «включить» ровно тогда, когда это значит истину.
    """
    raw_flag = payload.get(flag_key)
    return (
        int_or_none(payload.get(id_key)),
        None if raw_flag is None else bool(raw_flag),
    )


def _comma_list(raw) -> list[str]:
    """Набор, набранный одной строкой через запятую либо пришедший списком.

    Формы шлют такие наборы двумя видами: список, прочитанный как строка,
    лёг бы в колонку одним куском вида «['ООО Контур']». Своего здесь только
    разбор строки; дальше читает `str_list` — то же объявление, которым эти
    списки читают обе стороны в репозитории. Пустые, пробельные и не-строки
    выпадают там.
    """
    if isinstance(raw, str):
        raw = raw.split(",")
    return str_list(raw)


def read_company_spellings(raw) -> list[str]:
    """Написания компании из нагрузки формы.

    Приходят с одного экрана строкой через запятую, с другого — готовым
    списком, и читаются оба: не сойдись это, ни одно написание не нашлось бы
    при сведении компаний.

    Имя оставлено своё, хотя тело общее со стеком вакансии: читают его
    подборщик связи и форма компании, и увидеть на шве им надо, что
    просеиваются здесь именно написания.
    """
    return _comma_list(raw)


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


def _slashed(country: str | None, city: str | None) -> str | None:
    """Страна и город одной строкой — так же, как их пишет разбор объявления.

    Косая черта значит «страна и город»: висящая в конце, она читалась бы как
    потерянный город, поэтому одна названная половина стоит сама по себе.
    Разойдись это написание с тем, что кладёт разбор, отбор и статистика
    считали бы одно место двумя разными.
    """
    named = [part for part in (country, city) if part]
    return "/".join(named) if named else None


def read_new_vacancy_fields(payload: dict) -> dict:
    """Поля новой вакансии из нагрузки формы «добавить вакансию».

    Ключи названы колонками `Vacancy` затем, что репозиторий кладёт
    прочитанное в строку одним объектом: второе написание того же перечня
    разъехалось бы с первым молча.

    Название отдаётся строкой, а не пустотой, — как и у компании: слот
    отвечает на пустое «Название обязательно». Компания и человек приезжают
    номерами: их выбирают из заведённых карточек, и записанное строкой имя не
    связало бы вакансию ни с чьей.

    Чем просеяно и приведено остальное, сказано у тех, кто это делает:
    `normalize_enum`, `currency_sign` и `_slashed`.
    """
    return {
        "title": text_or_none(payload.get("title")) or "",
        "company_id": int_or_none(payload.get("company_id")),
        "hr_id": int_or_none(payload.get("hr_id")),
        "source_url": text_or_none(payload.get("source_url")),
        "location": _slashed(
            text_or_none(payload.get("country")), text_or_none(payload.get("city"))
        ),
        "remote": normalize_enum(payload.get("remote"), WORK_FORMATS),
        "grade": normalize_enum(payload.get("grade"), GRADES),
        "salary_min": int_or_none(payload.get("salary_min")),
        "salary_max": int_or_none(payload.get("salary_max")),
        "salary_currency": currency_sign(text_or_none(payload.get("salary_currency"))),
        # Двумя половинами, как их набирают двумя рядами пилюль: по ним
        # считается балл, и весят они по-разному. В колонку `stack` их
        # складывает репозиторий — там же, где это делает разбор поста.
        "stack_required": _comma_list(payload.get("stack_required")),
        "stack_preferred": _comma_list(payload.get("stack_preferred")),
        "description": text_or_none(payload.get("description")),
        "notes": text_or_none(payload.get("notes")),
        # Дату публикации набирают: из набранного её не вывести, а по ней
        # идут отбор «за последние дни» и давность в списке.
        "posted_at": moment_or_none(payload.get("posted_at")),
    }
