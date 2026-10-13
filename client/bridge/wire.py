"""Перевод внутренних значений в словари, которые читает окно."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from backend.domain.skill_names import skill_key
from backend.models import Blacklist
from client.bridge.media import _avatar_data_url, _media_url


def _iso(dt: datetime | None) -> str | None:
    """ISO-8601 с обязательным TZ-суффиксом, под JS `Date.parse`.

    SQLite + ``DateTime(timezone=True)`` хранит как text. Строки, записанные
    через ``server_default=func.now()`` (vacancy_status_history.changed_at,
    vacancy_event.created_at и т.п.) приходят обратно naive — без offset'а.
    Голый ``.isoformat()`` шлёт `"2026-05-07T12:34:56"` без `Z`/`+00:00`,
    а `Date.parse` без TZ интерпретирует строку как ЛОКАЛЬНОЕ время —
    свежий эвент превращается в «N часов назад» на величину TZ-оффсета.
    Naive значения трактуем как UTC (потому что вся запись идёт в UTC),
    aware — отдаём как есть.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _vacancy_mini_row_to_dict(v) -> dict:
    """Строка вакансии в боковом списке чужой карточки.

    Одна форма на три карточки — человека, компании и канала: списки эти
    рисует один и тот же кусок разметки, и разойдись поля, на одном экране
    пропала бы оценка, на другом — положение дел.

    Дата одна — заведения. Дата появления в посте лежала в нагрузке канала и
    до сведения, но её не читает ни один из трёх рисовальщиков: все берут
    `created_at`. Отдавать её всем троим значило бы размножить мёртвое поле, а
    у человека и компании оно ещё и разошлось бы с порядком — те списки
    отсортированы по дате заведения.
    """
    return {
        "id": v.id,
        "title": v.title or "",
        "status": v.status.value if v.status else "New",
        "score": v.score,
        "created_at": _iso(v.created_at),
    }


def _tg_creds_to_dict(tg) -> dict:
    """Учётные данные Telegram окну: три поля, пустые строки вместо отсутствия.

    Пустая строка, а не пустота, — по тому же доводу, что у поставщика модели
    ниже: этим ответом окно заполняет поля формы напрямую.

    Номер приложения уезжает строкой: форма его такой и покажет, а обратно он
    приезжает текстом и приводится к числу при входе (`login.read_credentials`).

    Спрашивают это двое — экран настроек и первый запуск, — и спрашивают одно и
    то же. Своё у каждого лежит рядом с зовом: настройкам нужны признаки «есть
    пароль» и «есть сеанс», первому запуску — сам пароль.

    `api_hash` уезжает открытым текстом: окно показывает его в поле ввода.
    """
    return {
        "api_id": str(tg.api_id) if tg else "",
        "api_hash": tg.api_hash if tg else "",
        "phone": tg.phone if tg else "",
    }


def _llm_provider_to_dict(cfg) -> dict:
    """Настройки поставщика модели окну: три поля, пустые строки вместо
    отсутствия.

    Пустая строка, а не пустота: поля формы окно заполняет этим ответом
    напрямую, и `null` показался бы в них словом «null». Собиралось это
    четырьмя телами — по два в мастере и в настройках, — и все четыре
    одинаковы: у поставщика в форме нет ничего, кроме адреса, ключа и имени
    модели.

    Ключ уезжает открытым текстом: окно показывает его в поле ввода, и
    звёздочки вместо него человек не смог бы поправить. В журнал он не
    попадает — за этим следит вымарывание в `backend/log_secrets.py`.
    """
    return {
        "base_url": cfg.base_url if cfg else "",
        "api_key": cfg.api_key if cfg else "",
        "model": cfg.model if cfg else "",
    }


def _enum_value(member) -> str | None:
    return member.value if member is not None else None


def _profile_to_dict(p, languages=None) -> dict | None:
    if p is None:
        return None
    return {
        "first_name": p.first_name,
        "last_name": p.last_name,
        "title": p.title,
        "email": p.email,
        "phone": p.phone,
        "location": p.location,
        "telegram_username": p.telegram_username,
        "github_url": p.github_url,
        "education": p.education,
        "free_preferences": p.free_preferences,
        "expected_salary": p.expected_salary,
        "expected_salary_currency": p.expected_salary_currency,
        "expected_salary_period": _enum_value(p.expected_salary_period),
        "first_name_latin": p.first_name_latin,
        "last_name_latin": p.last_name_latin,
        "gender": _enum_value(p.gender),
        "grades": list(p.grades or []),
        "work_format": list(p.work_format or []),
        "languages": [
            {"language": lang.language, "level": lang.level}
            for lang in (languages or [])
        ],
        "updated_at": _iso(p.updated_at),
    }


def _skill_to_dict(s) -> dict:
    return {
        "id": s.id,
        "category": s.category,
        "name": s.name,
        "level": s.level,
        "aliases": list(s.aliases or []),
    }


def _exp_to_dict(e) -> dict:
    return {
        "id": e.id,
        "company": e.company,
        "company_url": e.company_url,
        "role": e.role,
        "start_date": e.start_date.isoformat() if e.start_date else None,
        "end_date": e.end_date.isoformat() if e.end_date else None,
        "achievements": list(e.achievements or []),
        "responsibilities": list(e.responsibilities or []),
        "skill_names": [s.name for s in (e.skills or [])],
    }


def _project_to_dict(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "url": p.url,
        "about": list(p.about),
        "skill_names": [s.name for s in p.skills],
    }


def _stack_items(stack, matched_set: set[str]) -> list[dict]:
    out: list[dict] = []
    for item in (stack or []):
        if isinstance(item, str) and item:
            out.append(
                {"name": item, "matched": skill_key(item) in matched_set}
            )
    return out


def _company_name(v) -> str | None:
    """Имя компании вакансии: связанная карточка перебивает написание объявления.

    Ради этого связывание и делают: одна компания под пятью написаниями
    перестаёт выглядеть пятью разными. Пока связи нет, окно показывает то, что
    написано в самом объявлении, — иначе строка осталась бы вовсе без компании.

    Читают это карточка и строка списка, и читать они обязаны одно: разойдись
    правило, одна и та же вакансия называла бы компанию по-разному на двух
    экранах.
    """
    return v.company.name if v.company is not None else v.company_name


def _hr_face(hr) -> dict:
    """Человек строкой со снимком — чем его показывают чужие карточки.

    Полей четыре из полутора десятков, что есть у записи: и карточка вакансии,
    и боковой список карточки компании показывают человека одной строкой, а не
    разворачивают его целиком — для этого у него своя карточка.
    """
    return {
        "id": hr.id,
        "name": hr.name,
        "telegram_username": hr.telegram_username,
        "avatar": _avatar_data_url(hr.avatar),
    }


def _status_change(row) -> dict:
    """Одна смена статуса в истории вакансии.

    Прежний статус бывает пустым — у самой первой записи: до неё вакансии не
    было вовсе, и «из чего» здесь не из чего взять.
    """
    return {
        "id": row.id,
        "previous_status": _enum_value(row.previous_status),
        "status": row.status.value,
        "explanation": row.explanation,
        "applied": row.applied,
        "source": row.source.value,
        "changed_at": _iso(row.changed_at),
    }


def _vacancy_event(row) -> dict:
    """Одна запись в ленте вакансии: что с ней случилось и когда."""
    return {
        "id": row.id,
        "kind": row.kind,
        "payload": row.payload,
        "created_at": _iso(row.created_at),
    }


def _contact(c) -> dict:
    return {"id": c.id, "value": c.value, "added_by": c.added_by.value}


def _salary(v) -> dict:
    """Зарплата на проводе: строка объявления и разобранные из неё числа.

    Пилюлю окно собирает из чисел, а не из строки: разбор велит модели брать
    зарплату дословно, и в строке приезжает написанное автором поста — со
    служебным зачином и эмодзи. Строка при этом остаётся: её показывает
    исходный текст объявления.

    Общая на карточку и на строку списка: пилюля у них одна и та же, и
    разойдись наборы полей, в одном из мест она замолчала бы.
    """
    return {
        "salary": v.salary,
        "salary_min": v.salary_min,
        "salary_max": v.salary_max,
        "salary_currency": v.salary_currency,
    }


def _source(v) -> dict:
    """Откуда вакансия: канал или агрегатор, номер поста и адрес её страницы.

    «Поиск по сети» назван отдельным признаком: его имя — способ поиска, а не
    место, откуда вакансия пришла, и окно подписывает её иначе.
    """
    return {
        "channel_username": v.channel.username if v.channel is not None else None,
        "aggregator_name": v.aggregator.name if v.aggregator is not None else None,
        "from_web_search": v.aggregator is not None and v.aggregator.host is None,
        "source_msg_id": v.source_msg_id,
        "source_url": v.source_url,
    }


def _vacancy_detail_to_dict(
    detail, matched_set: set[str], score_threshold: int,
) -> dict:
    """Карточка вакансии — всё, что показывает её правая половина.

    Откат к разобранным строкам вакансии есть **только у названия компании**
    (`_company_name`): её человек видит и у непривязанной. У остальных троих
    отката нет — не привязана, значит пусто: сайт и `@username` канала брать
    неоткуда вовсе, а у человека разобранная строка есть (`hr_contact`), и
    карточка её всё равно не показывает. Окно на это отвечает кнопкой
    «привязать», а не пустой строкой без действия.
    """
    v = detail.vacancy
    return {
        "id": v.id,
        "status": v.status.value,
        "score": v.score,
        "score_threshold": score_threshold,
        "title": v.title,
        "description": v.description,
        "raw_text": v.raw_text,
        "company_id": v.company_id,
        "company_name": _company_name(v),
        "company_website": v.company.website if v.company is not None else None,
        "hr": _hr_face(v.hr) if v.hr is not None else None,
        "grade": v.grade,
        **_salary(v),
        "remote": v.remote,
        "location": v.location,
        **_source(v),
        "stack": _stack_items(v.stack, matched_set),
        "notes": v.notes,
        "contacts": [_contact(c) for c in detail.contacts],
        "posted_at": _iso(v.posted_at),
        "created_at": _iso(v.created_at),
        "history": [_status_change(h) for h in detail.history],
        "events": [_vacancy_event(e) for e in detail.events],
        "has_screening": detail.has_screening,
    }


def _hr_picker_row_to_dict(item) -> dict:
    """Строка человека: и в подборщике при вакансии, и в списке контактов.

    Includes ``unread_count`` and ``is_blacklisted`` for the lime unread
    badge / red blacklist marker in Contacts/HR; the picker ignores them.
    """
    hr = item.hr
    return {
        "id": hr.id,
        "name": hr.name,
        "telegram_username": hr.telegram_username,
        "telegram_user_id": hr.telegram_user_id,
        "vacancy_count": item.vacancy_count,
        "last_company_name": item.last_company_name,
        "unread_count": item.unread_count,
        "is_blacklisted": item.is_blacklisted,
        "avatar": _avatar_data_url(hr.avatar),
    }


def _hr_mini_row_to_dict(hr, vacancy_count: int) -> dict:
    """Строка человека в боковом списке карточки компании.

    Сам человек — тем же `_hr_face`, что и в карточке вакансии: строка со
    снимком у них одна. Своё здесь только счёт, и он не тот, что у подборщика:
    там счёт по всем вакансиям человека и лежит полем прочитанного, а сюда
    приходит отдельным доводом. Непрочитанные, последняя компания и отметка
    заслона сюда не едут вовсе: карточка рассказывает про компанию, а не про
    человека целиком.
    """
    return {**_hr_face(hr), "vacancy_count": vacancy_count}


def _message_row_to_dict(m) -> dict:
    """Письмо переписки — тем, из чего окно рисует пузырь.

    Вложение уезжает адресом, а не байтами: через канал байты не ходят.
    """
    return {
        "id": m.id,
        "tg_message_id": m.tg_message_id,
        "is_incoming": m.is_incoming,
        "text": m.text,
        "sent_at": _iso(m.sent_at),
        "read_at": _iso(m.read_at),
        "vacancy_id": m.vacancy_id,
        "is_edited": m.is_edited,
        "is_deleted": m.is_deleted,
        "media_kind": m.media_kind,
        "media_path": _media_url(m.media_path),
        "media_name": m.media_name,
    }


def _blacklist_row_to_dict(row: Blacklist) -> dict:
    """Строка чёрного списка.

    Роды объявлены один раз — в `backend/models/settings.py`, — и мост чужой
    род отбивает до записи. Окно различает их и красит чипы.
    """
    return {
        "id": row.id,
        "kind": row.kind,
        "value": row.value,
        "reason": row.reason,
        "active": bool(row.active),
        "created_at": _iso(row.created_at),
    }


def _channel_row_to_dict(item) -> dict:
    """Строка канала в списке контактов.

    Avatar carried as base64 data URL; same convention as HR rows.
    """
    ch = item.channel
    return {"id": ch.id, **_channel_fields(ch),
            "vacancy_count": item.vacancy_count, "is_blacklisted": item.is_blacklisted}


def _channel_card_to_dict(detail) -> dict:
    """Карточка канала: сам канал, его числа и значение отметки отсева."""
    ch = detail.channel
    return {"channel_id": ch.id, **_channel_fields(ch),
            "stats": _source_stats_to_dict(detail.stats),
            "blacklist_value": detail.blacklist_value}


def _channel_fields(ch) -> dict:
    """Что о канале показывают и строка списка, и карточка."""
    return {
        "username": ch.username,
        "title": ch.title,
        "is_active": bool(ch.is_active),
        "avatar": _avatar_data_url(ch.avatar),
    }


def _company_picker_row_to_dict(item) -> dict:
    """Строка компании: и в подборщике при вакансии, и в списке контактов.

    ``is_blacklisted`` едет следом ради красной отметки в списке.
    """
    co = item.company
    return {
        "id": co.id,
        "name": co.name,
        "website": co.website,
        "aliases": list(co.aliases or []),
        "vacancy_count": item.vacancy_count,
        "is_blacklisted": item.is_blacklisted,
    }


def _vacancy_list_row_to_dict(
    v, matched_set: set[str], activity_by_id: dict[int, Any] | None = None
) -> dict:
    """Строка вакансии в списке. Имя компании выбирает `_company_name` — то же,
    что и в карточке. Each stack item is paired with a ``matched`` flag against
    the casefolded profile skills + aliases set so the UI can highlight relevant
    chips."""
    company = _company_name(v)
    channel_username = v.channel.username if v.channel is not None else None
    last_activity = None
    if activity_by_id:
        last_activity = activity_by_id.get(int(v.id))
    return {
        "id": v.id,
        "status": v.status.value,
        "score": v.score,
        "title": v.title,
        "description": v.description,
        "notes": v.notes,
        "company": company,
        "company_id": v.company_id,
        "company_raw_name": v.company_name,
        "hr_name": v.hr.name if v.hr is not None else None,
        "hr_username": v.hr.telegram_username if v.hr is not None else None,
        "hr_id": v.hr_id,
        "channel_username": channel_username,
        "grade": v.grade,
        **_salary(v),
        "remote": v.remote,
        "stack": _stack_items(v.stack, matched_set),
        "posted_at": _iso(v.posted_at),
        "created_at": _iso(v.created_at),
        "last_activity_at": _iso(last_activity),
    }


def _aggregator_row_to_dict(row) -> dict:
    """Строка агрегатора на экране «Агрегаторы»; «Поиск по сети» — строка без хоста."""
    return {
        "id": row.id,
        "name": row.name,
        "host": row.host,
        "is_active": bool(row.is_active),
        "is_logged_in": bool(row.is_logged_in),
        "is_web_search": row.host is None,
        "avatar": _avatar_data_url(row.avatar),
    }


def _aggregator_list_row_to_dict(row, vacancy_count: int, barred: bool) -> dict:
    """Строка списка агрегаторов: сам агрегатор, счёт его вакансий и отметка отсева."""
    return {**_aggregator_row_to_dict(row), "vacancy_count": vacancy_count, "is_blacklisted": barred}


def _screening_to_dict(shown) -> dict:
    """Скрининг одного отклика для окна: куда ушёл отклик и реплики по порядку."""
    return {"target": shown.target,
            "lines": [{"from_us": from_us, "text": text} for from_us, text in shown.lines]}


def _source_stats_to_dict(stats) -> dict:
    """Числа карточки источника — канала или агрегатора; см. `SourceStats`.

    Полем к полю: новое поле чисел доезжает до окна само, а не выпадает молча.
    """
    return asdict(stats)
