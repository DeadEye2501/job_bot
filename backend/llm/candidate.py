"""Сведения о кандидате в том виде, в каком они уходят в промпт."""


from dataclasses import dataclass, field

from backend.models import Profile
from backend.models import ProfileLanguage
from backend.models import ProfileSkill
from backend.incoming import str_list


@dataclass(frozen=True)
class CandidateLanguage:
    """Один язык кандидата с CEFR-уровнем (или 'native')."""

    name: str
    level: str  # "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "native"


@dataclass(frozen=True)
class CandidateProfile:
    """Всё, что модель знает о кандидате: анкета и его навыки.

    Единым объектом, а не доводами: порознь у вердикта пригодности их
    набиралось шесть, и линт краснел. Навыки лежат здесь же, потому что
    уходят в то же наставление и берутся из того же слепка настроек.

    Заполняет их не сборщик, а зовущий: `build_candidate_profile` читает
    анкету, а навыки лежат отдельным слепком у конвейера, и он дописывает их
    сюда сам. Соберёшь профиль в новом месте и не допишешь — наставление
    получит прочерк вместо навыков, и заметить это будет нечем.
    """

    title: str | None = None
    location: str | None = None
    grades: list[str] = field(default_factory=list)
    work_formats: list[str] = field(default_factory=list)
    languages: list[CandidateLanguage] = field(default_factory=list)
    free_preferences: str | None = None
    known_skills: list[ProfileSkill] = field(default_factory=list)


def format_languages(languages: list[CandidateLanguage] | None) -> str:
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


def format_text(text: str | None) -> str:
    """Свободный текст в слот промпта, либо «—», если пусто.

    Прочерк, а не пустота: незаполненный слот оставил бы в промпте
    оборванную строку, и модель дописала бы её сама.
    """
    s = (text or "").strip()
    return s if s else "—"


def format_known_skills(skills) -> str:
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


def candidate_languages(rows: list[ProfileLanguage]) -> list[CandidateLanguage]:
    """Языки анкеты в том виде, в каком их пишет `format_languages`."""
    return [CandidateLanguage(name=row.language, level=row.level) for row in rows]


def build_candidate_profile(
    profile: Profile | None,
    languages: list[ProfileLanguage],
) -> CandidateProfile:
    """Собирает срез данных профиля для LLM-валидатора. Если профиль ещё не
    создан — возвращает пустой CandidateProfile (валидатор подставит '—' и
    относится к этому как «нет ограничений»).

    Навыки здесь не заполняются: они живут своим слепком у конвейера, и
    дописывает их зовущий (см. `CandidateProfile`)."""
    if profile is None:
        return CandidateProfile()
    return CandidateProfile(
        title=profile.title,
        location=profile.location,
        grades=list(profile.grades or []),
        work_formats=list(profile.work_format or []),
        languages=candidate_languages(languages),
        free_preferences=profile.free_preferences,
    )
