"""Перевод внутренних значений в словари, которые читает окно."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.domain.scoring import skill_key
from backend.models import Blacklist
from client.bridge.media import _avatar_data_url


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


def _stack_items(stack, matched_set: set[str]) -> list[dict]:
    out: list[dict] = []
    for item in (stack or []):
        if isinstance(item, str) and item:
            out.append(
                {"name": item, "matched": skill_key(item) in matched_set}
            )
    return out


def _vacancy_detail_to_dict(
    detail, matched_set: set[str], score_threshold: int,
) -> dict:
    """Detail-pane payload. Linked Company / HR / Channel fields fall back
    to the raw parsed strings on the vacancy when the FK isn't set, so the
    UI can always render *something* without lazy-loading."""
    v = detail.vacancy
    company_name = v.company.name if v.company is not None else v.company_name
    company_website = v.company.website if v.company is not None else None
    channel_username = v.channel.username if v.channel is not None else None
    hr_block = None
    if v.hr is not None:
        hr_block = {
            "id": v.hr.id,
            "name": v.hr.name,
            "telegram_username": v.hr.telegram_username,
            "avatar": _avatar_data_url(v.hr.avatar),
        }
    return {
        "id": v.id,
        "status": v.status.value,
        "score": v.score,
        "score_threshold": score_threshold,
        "title": v.title,
        "description": v.description,
        "raw_text": v.raw_text,
        "company_id": v.company_id,
        "company_name": company_name,
        "company_website": company_website,
        "hr": hr_block,
        "grade": v.grade,
        "salary": v.salary,
        "remote": v.remote,
        "location": v.location,
        "channel_username": channel_username,
        "source_msg_id": v.source_msg_id,
        "source_url": v.source_url,
        "stack": _stack_items(v.stack, matched_set),
        "notes": v.notes,
        "posted_at": _iso(v.posted_at),
        "created_at": _iso(v.created_at),
        "history": [
            {
                "id": h.id,
                "previous_status": h.previous_status.value if h.previous_status else None,
                "status": h.status.value,
                "explanation": h.explanation,
                "applied": h.applied,
                "source": h.source.value,
                "changed_at": _iso(h.changed_at),
            }
            for h in detail.history
        ],
        "events": [
            {
                "id": e.id,
                "kind": e.kind,
                "payload": e.payload,
                "created_at": _iso(e.created_at),
            }
            for e in detail.events
        ],
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
        "is_blacklisted": getattr(item, "is_blacklisted", False),
        "avatar": _avatar_data_url(hr.avatar),
    }


def _blacklist_row_to_dict(row: Blacklist) -> dict:
    """Строка чёрного списка.

    `kind` — свободная строка (исторически использовались "hr", "company";
    добавляем "keyword", "channel"). Frontend различает кинды и красит чипы.
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
    return {
        "id": ch.id,
        "username": ch.username,
        "title": ch.title,
        "is_active": bool(ch.is_active),
        "vacancy_count": item.vacancy_count,
        "avatar": _avatar_data_url(ch.avatar),
        "is_blacklisted": getattr(item, "is_blacklisted", False),
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
        "is_blacklisted": getattr(item, "is_blacklisted", False),
    }


def _vacancy_list_row_to_dict(
    v, matched_set: set[str], activity_by_id: dict[int, Any] | None = None
) -> dict:
    """Строка вакансии в списке. Linked Company.name wins over the
    raw vacancy.company_name; falls back to raw if no FK is set. Each stack
    item is paired with a ``matched`` flag against the casefolded profile
    skills + aliases set so the UI can highlight relevant chips."""
    if v.company is not None:
        company = v.company.name
    else:
        company = v.company_name
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
        "salary": v.salary,
        "remote": v.remote,
        "stack": _stack_items(v.stack, matched_set),
        "posted_at": _iso(v.posted_at),
        "created_at": _iso(v.created_at),
        "last_activity_at": _iso(last_activity),
    }
