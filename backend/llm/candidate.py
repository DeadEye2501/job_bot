"""Сведения о кандидате в том виде, в каком они уходят в промпт."""


from dataclasses import dataclass, field

from backend.models import Profile
from backend.models import ProfileLanguage
from backend.payloads import str_list

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


def _format_labels(values: list[str] | None, labels: dict[str, str]) -> str:
    """Подписи выбранных значений через запятую либо «—», если выбирать
    нечего или ни одно значение не нашлось в справочнике подписей.
    """
    if not values:
        return "—"
    parts: list[str] = []
    for value in values:
        key = (value or "").strip().lower()
        if key in labels:
            parts.append(labels[key])
    return ", ".join(parts) if parts else "—"


def _format_grades(grades: list[str] | None) -> str:
    """'middle, senior, lead/team-lead' либо '—' если пусто."""
    return _format_labels(grades, _GRADE_LABELS_RU)


def _format_work_formats(formats: list[str] | None) -> str:
    """'удалёнка, гибрид' либо '—' если пусто."""
    return _format_labels(formats, _FORMAT_LABELS_RU)


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


def _format_text(text: str | None) -> str:
    """Свободный текст в слот промпта, либо «—», если пусто.

    Прочерк, а не пустота: незаполненный слот оставил бы в промпте
    оборванную строку, и модель дописала бы её сама.
    """
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
        aliases = str_list(getattr(s, "aliases", None))
        if aliases:
            lines.append(f"- {name} — {', '.join(aliases)}")
        else:
            lines.append(f"- {name}")
    return "\n".join(lines) if lines else "—"


def _build_candidate_profile(
    profile: Profile | None,
    languages: list[ProfileLanguage],
) -> CandidateProfile:
    """Собирает срез данных профиля для LLM-валидатора. Если профиль ещё не
    создан — возвращает пустой CandidateProfile (валидатор подставит '—' и
    относится к этому как «нет ограничений»)."""
    if profile is None:
        return CandidateProfile()
    return CandidateProfile(
        title=profile.title,
        location=profile.location,
        grades=list(profile.grades or []),
        work_formats=list(profile.work_format or []),
        languages=[
            CandidateLanguage(name=l.language, level=l.level) for l in languages
        ],
        free_preferences=profile.free_preferences,
    )
