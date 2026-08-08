"""Сведения о кандидате в том виде, в каком они уходят в промпт."""


from dataclasses import dataclass, field

_GRADE_LABELS_RU = {
    "junior": "junior",
    "middle": "middle",
    "senior": "senior",
    "lead": "lead/team-lead",
}


_FORMAT_LABELS_RU = {
    "remote": "удалёнка",
    "hybrid": "гибрид",
    "office": "офис",
}


@dataclass(frozen=True)
class CandidateLanguage:
    """Один язык кандидата с CEFR-уровнем (или 'native')."""

    name: str
    level: str  # "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "native"


@dataclass(frozen=True)
class CandidateProfile:
    """Срез данных профиля, нужный LLM-валидатору вакансии. Передаётся как
    единый объект, чтобы в сигнатуре validate_vacancy_fit не висело пять
    позиционных аргументов."""

    title: str | None = None
    location: str | None = None
    grades: list[str] = field(default_factory=list)
    work_formats: list[str] = field(default_factory=list)
    languages: list[CandidateLanguage] = field(default_factory=list)
    free_preferences: str | None = None


def _format_grades(grades: list[str] | None) -> str:
    """'middle, senior, lead/team-lead' либо '—' если пусто."""
    if not grades:
        return "—"
    parts: list[str] = []
    for g in grades:
        key = (g or "").strip().lower()
        if key in _GRADE_LABELS_RU:
            parts.append(_GRADE_LABELS_RU[key])
    return ", ".join(parts) if parts else "—"


def _format_work_formats(formats: list[str] | None) -> str:
    """'удалёнка, гибрид' либо '—' если пусто."""
    if not formats:
        return "—"
    parts: list[str] = []
    for f in formats:
        key = (f or "").strip().lower()
        if key in _FORMAT_LABELS_RU:
            parts.append(_FORMAT_LABELS_RU[key])
    return ", ".join(parts) if parts else "—"


def _format_languages(languages: list[CandidateLanguage] | None) -> str:
    """'Русский — native, Английский — A2' либо '—' если пусто."""
    if not languages:
        return "—"
    parts: list[str] = []
    for lang in languages:
        name = (lang.name or "").strip()
        if not name:
            continue
        lvl = (lang.level or "").strip()
        if not lvl:
            # пустой уровень не пропускаем как «— —» — пропускаем сам
            # элемент, чтобы LLM не путал «—» с реальным CEFR-токеном
            continue
        parts.append(f"{name} — {lvl}")
    return ", ".join(parts) if parts else "—"


def _format_free_preferences(text: str | None) -> str:
    """Свободный текст личных предпочтений, либо '—' если пусто."""
    s = (text or "").strip()
    return s if s else "—"


def _format_known_skills(skills) -> str:
    """Render the user's profile_skills + aliases as a parseable bullet list
    for the parse_vacancy prompt's stack-normalization section. Empty list
    becomes "—" so the prompt slot stays grammatically valid."""
    if not skills:
        return "—"
    lines = []
    for s in skills:
        name = (getattr(s, "name", "") or "").strip()
        if not name:
            continue
        aliases = [
            a.strip()
            for a in (getattr(s, "aliases", None) or [])
            if isinstance(a, str) and a.strip()
        ]
        if aliases:
            lines.append(f"- {name} — {', '.join(aliases)}")
        else:
            lines.append(f"- {name}")
    return "\n".join(lines) if lines else "—"
