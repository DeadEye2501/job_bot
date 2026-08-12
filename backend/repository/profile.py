"""Хранение анкеты кандидата."""

import logging
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cv_parser import ParsedCv
from backend.domain.skill_names import index_by_key, skill_key
from backend.models import (
    AppSetting,
    Profile,
    ProfileExperience,
    ProfileLanguage,
    ProfileSkill,
    profile_experience_skills,
)
from backend.payloads import str_list

logger = logging.getLogger(__name__)


async def _wipe_experience(session: AsyncSession) -> None:
    """Стереть места работы вместе со связками «место — навык».

    Порядок несущий: проверка внешних ключей у этого движка включена, и
    сотри места первыми — база отказала бы, потому что на них ещё смотрят
    связки. Стирают опыт две дороги — разбор резюме и запись из окна, — и
    порядок у них один.
    """
    await session.execute(delete(profile_experience_skills))
    await session.execute(delete(ProfileExperience))


def _index_skill_keys(
    lookup: dict[str, ProfileSkill],
    names: tuple[str, ...],
    row: ProfileSkill,
    where: str,
) -> None:
    """Записать строку навыка под ключи её написаний; первая выигрывает.

    Само правило живёт в `domain/skill_names.index_by_key`; здесь остаётся
    жалоба. Жалуемся громко и только на спор двух разных строк: в анкете
    такого быть не должно, а схема не запрещает. Столкновение написания с
    собственным названием строки — не спор, а обычное дело.
    """
    for _name, key, existing in index_by_key(lookup, names, row):
        if existing is not row:
            logger.warning(
                "%s: skill key %r collides between %r and %r, keeping first",
                where, key, existing.name, row.name,
            )


def _skills_by_key(rows: list[ProfileSkill]) -> dict[str, ProfileSkill]:
    """Навыки анкеты по ключу их названия; прозвища сюда не идут.

    Прозвища знает разбор резюме, потому что стек места работы приходит от
    модели любым написанием. Окно же присылает выбранное из списка, то есть
    само название, и лишний ключ там только множил бы столкновения.
    """
    lookup: dict[str, ProfileSkill] = {}
    for row in rows:
        _index_skill_keys(lookup, (row.name,), row, "save_experience")
    return lookup


async def save_parsed_cv(
    session: AsyncSession, parsed: ParsedCv, *, cv_path: str | None = None
) -> None:
    """Replace the single Profile (and its skills/experience) with parsed data.

    If ``cv_path`` is provided, also upserts ``app_settings.cv_path`` in the
    same transaction so the wizard's "parse-and-save" step is atomic
    (otherwise a crash between the two writes leaves a parsed profile with
    no recorded source file).

    Caller must wrap in ``session.begin()``. Wipes existing rows because the
    wizard implies a fresh write — partial merging would cause stale skills
    to silently linger.
    """
    await _wipe_experience(session)
    await session.execute(delete(ProfileSkill))
    await session.execute(delete(ProfileLanguage))
    await session.execute(delete(Profile))
    await session.flush()

    p = parsed.profile
    profile = Profile(
        first_name=p.first_name,
        last_name=p.last_name,
        title=p.title,
        email=p.email,
        phone=p.phone,
        location=p.location,
        telegram_username=p.telegram_username,
        github_url=p.github_url,
        education=p.education,
        work_format=list(p.work_format),
        grades=list(p.grades),
        free_preferences=p.free_preferences,
    )
    session.add(profile)
    await session.flush()

    # Стирание внутри писателя здесь холостое — таблица снесена целиком выше.
    # Так и оставлено: свой цикл ради экономии одного запроса на разбор резюме
    # означал бы второе место, знающее устройство строки языка.
    await replace_profile_languages(
        session,
        profile.id,
        [(lang.language, lang.level) for lang in parsed.languages],
    )

    skill_lookup: dict[str, ProfileSkill] = {}
    for s in parsed.skills:
        row = ProfileSkill(
            profile_id=profile.id,
            category=s.category,
            name=s.name,
            level=s.level,
            aliases=list(s.aliases),
        )
        session.add(row)
        _index_skill_keys(skill_lookup, (s.name, *s.aliases), row, "save_parsed_cv")
    await session.flush()

    for e in parsed.experience:
        exp = ProfileExperience(
            profile_id=profile.id,
            company=e.company,
            company_url=e.company_url,
            role=e.role,
            start_date=e.start_date,
            end_date=e.end_date,
            achievements=list(e.achievements),
            responsibilities=list(e.responsibilities),
        )
        for tech in e.stack:
            key = skill_key(tech)
            row = skill_lookup.get(key) if key else None
            if row is not None:
                exp.skills.append(row)
            else:
                logger.warning(
                    "save_parsed_cv: experience %r stack item %r not matched to any ProfileSkill",
                    e.company, tech,
                )
        session.add(exp)
    await session.flush()

    if cv_path is not None:
        existing = await session.get(AppSetting, "cv_path")
        if existing is None:
            session.add(AppSetting(key="cv_path", value=cv_path))
        else:
            existing.value = cv_path
        await session.flush()

    logger.info(
        "Profile replaced: languages=%d skills=%d experiences=%d cv_path=%s",
        len(parsed.languages),
        len(parsed.skills),
        len(parsed.experience),
        cv_path,
    )


async def list_skills(session: AsyncSession) -> list[ProfileSkill]:
    """All ProfileSkill rows ordered by id (preserves user-set order).

    Порядок здесь не украшение: столкновение ключей навыков разрешается в
    пользу первого (`domain/skill_names.index_by_key`), и без `order_by`
    «первый» назначал бы читатель, ничем этого не обещавший.
    """
    return list(
        (await session.scalars(select(ProfileSkill).order_by(ProfileSkill.id))).all()
    )


async def list_experience(session: AsyncSession) -> list[ProfileExperience]:
    """All ProfileExperience rows newest-first, with skills relationship loaded."""
    from sqlalchemy.orm import selectinload

    return list(
        (
            await session.scalars(
                select(ProfileExperience)
                .options(selectinload(ProfileExperience.skills))
                .order_by(ProfileExperience.start_date.desc())
            )
        ).all()
    )


async def save_skills(
    session: AsyncSession,
    rows: list[dict],
    profile_id: int,
) -> None:
    """Update / insert / delete skills by id, preserving experience links.

    Each row may carry an integer ``id`` (existing row → UPDATE) or a None
    / string id (new row → INSERT). Rows whose ids are not present in the
    payload get DELETEd along with their junction entries. UPDATEing a row
    leaves its row id stable, so profile_experience_skills naturally
    survives even if the user renamed the skill.

    Caller wraps in ``session.begin()``.
    """
    existing = {s.id: s for s in await list_skills(session)}
    keep_ids: set[int] = set()

    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        category = (row.get("category") or "Общее").strip() or "Общее"
        try:
            level = int(row.get("level") or 1)
        except (TypeError, ValueError):
            level = 1
        aliases = str_list(row.get("aliases"))
        rid = row.get("id")
        rid_int = rid if isinstance(rid, int) else None

        if rid_int is not None and rid_int in existing:
            s = existing[rid_int]
            s.category = category
            s.name = name
            s.level = level
            s.aliases = aliases
            keep_ids.add(rid_int)
        else:
            session.add(ProfileSkill(
                profile_id=profile_id,
                category=category,
                name=name,
                level=level,
                aliases=aliases,
            ))

    # Delete rows the user removed. Junction has no ON DELETE CASCADE on
    # SQLite by default, so wipe the links explicitly first.
    drop_ids = set(existing.keys()) - keep_ids
    for sid in drop_ids:
        await session.execute(
            delete(profile_experience_skills).where(
                profile_experience_skills.c.skill_id == sid
            )
        )
        await session.delete(existing[sid])
    await session.flush()
    logger.debug(
        "Saved skills: kept=%d dropped=%d", len(keep_ids), len(drop_ids)
    )


class SaveExperienceError(ValueError):
    """Raised on validation failure during save_experience.

    Attribute ``index`` is the 1-based row number that failed; ``problem``
    describes what's wrong in human-readable Russian for the UI.
    """

    def __init__(self, index: int, problem: str) -> None:
        self.index = index
        self.problem = problem
        super().__init__(f"Запись #{index}: {problem}")


async def save_experience(
    session: AsyncSession,
    rows: list[dict],
    profile_id: int,
) -> None:
    """Replace all ProfileExperience rows + their skill links.

    Validates eagerly: on the first invalid row the call raises
    ``SaveExperienceError`` BEFORE any DB writes, so the caller can show a
    targeted error and the user doesn't lose data they typed. Skills are
    matched to existing ProfileSkill rows by name; unknown names are
    dropped silently (UI's skill picker only offers existing skills).

    Caller wraps in ``session.begin()``.
    """
    skills_by_name = _skills_by_key(await list_skills(session))

    # Validate everything first — fail fast, no half-applied state.
    parsed_rows: list[tuple[dict, date, date | None]] = []
    for i, row in enumerate(rows, start=1):
        company = (row.get("company") or "").strip()
        role = (row.get("role") or "").strip()
        start_iso = (row.get("start_date") or "").strip()
        if not company:
            raise SaveExperienceError(i, "не заполнено название компании")
        if not role:
            raise SaveExperienceError(i, "не заполнена должность")
        if not start_iso:
            raise SaveExperienceError(i, "не заполнена дата начала")
        try:
            start_date = date.fromisoformat(start_iso)
        except ValueError:
            raise SaveExperienceError(i, f"неверная дата начала: {start_iso!r}")
        end_iso = (row.get("end_date") or "").strip()
        end_date: date | None = None
        if end_iso:
            try:
                end_date = date.fromisoformat(end_iso)
            except ValueError:
                raise SaveExperienceError(
                    i, f"неверная дата окончания: {end_iso!r}"
                )
        parsed_rows.append((row, start_date, end_date))

    await _wipe_experience(session)
    await session.flush()

    for row, start_date, end_date in parsed_rows:
        company_url = (row.get("company_url") or "").strip() or None
        exp = ProfileExperience(
            profile_id=profile_id,
            company=row["company"].strip(),
            company_url=company_url,
            role=row["role"].strip(),
            start_date=start_date,
            end_date=end_date,
            achievements=str_list(row.get("achievements")),
            responsibilities=str_list(row.get("responsibilities")),
        )
        for sname in (row.get("skill_names") or []):
            s = skills_by_name.get(skill_key(str(sname)))
            if s is not None:
                exp.skills.append(s)
        session.add(exp)
    await session.flush()
    logger.debug("Saved experiences: %d rows", len(parsed_rows))


async def get_profile(session: AsyncSession) -> Profile | None:
    """Return the single Profile row, if any."""
    return (await session.scalars(select(Profile).limit(1))).first()


async def upsert_profile(session: AsyncSession, **fields) -> Profile:
    """Update the single Profile row's basic fields, or create it.

    Caller must wrap in ``session.begin()``. Skills and experience are NOT
    touched here — those have their own write paths.
    """
    profile = await get_profile(session)
    if profile is None:
        profile = Profile(**fields)
        session.add(profile)
    else:
        for key, value in fields.items():
            setattr(profile, key, value)
    await session.flush()
    logger.debug("Profile upserted (fields=%s)", list(fields.keys()))
    return profile


async def list_profile_languages(
    session: AsyncSession,
) -> list[ProfileLanguage]:
    """Return all profile_language rows ordered by id (insertion order)."""
    rows = await session.scalars(
        select(ProfileLanguage).order_by(ProfileLanguage.id)
    )
    return list(rows)


async def replace_profile_languages(
    session: AsyncSession,
    profile_id: int,
    items: list[tuple[str, str]],
) -> None:
    """Wipe and re-insert profile_language rows for ``profile_id``.

    Caller must wrap in ``session.begin()``. The table is small (1-5 rows
    per profile), so a full replace is simpler than diff-and-update and
    keeps the (profile_id, language) uniqueness invariant trivially true.
    """
    await session.execute(
        delete(ProfileLanguage).where(
            ProfileLanguage.profile_id == profile_id
        )
    )
    await session.flush()
    for language, level in items:
        session.add(
            ProfileLanguage(
                profile_id=profile_id, language=language, level=level
            )
        )
    await session.flush()
    logger.debug("Profile languages replaced (count=%d)", len(items))


async def build_profile_block(session: AsyncSession) -> str:
    """Текстовый блок «Информация о кандидате» для cover-letter промпта.

    Собирает имя/роль/локацию/годы опыта (вычисляются по самой ранней
    ProfileExperience), скиллы по категориям и список мест работы. Если
    ``Profile.free_preferences`` заполнен — добавляется отдельной секцией
    «Дополнительно», чтобы LLM могла учесть пожелания (про релокацию, гео,
    специфичные предпочтения).
    """
    profile = await get_profile(session)
    if profile is None:
        return ""

    skills = await list_skills(session)
    experiences = await list_experience(session)

    skills_by_cat: dict[str, list[str]] = {}
    for s in skills:
        skills_by_cat.setdefault(s.category, []).append(s.name)
    skills_lines = [f"- {cat}: {', '.join(names)}" for cat, names in skills_by_cat.items()]

    # Незаполненные поля (None в БД) пропускаем целиком, иначе LLM получит
    # «Имя: None None» / «Роль: None» и попытается включить это в письмо.
    full_name = " ".join(
        p for p in (profile.first_name, profile.last_name) if p
    ).strip()
    header_lines: list[str] = []
    if full_name:
        header_lines.append(f"Имя: {full_name}")
    if profile.title:
        header_lines.append(f"Роль: {profile.title}")
    if profile.location:
        header_lines.append(f"Локация: {profile.location}")
    if experiences:
        min_start = min(e.start_date for e in experiences)
        today = date.today()
        years = today.year - min_start.year - (
            (today.month, today.day) < (min_start.month, min_start.day)
        )
        years = max(years, 0)
        header_lines.append(f"Опыт: {years}+ лет в IT")

    exp_lines = []
    for e in experiences:
        end = e.end_date.strftime("%m.%Y") if e.end_date else "настоящее время"
        start = e.start_date.strftime("%m.%Y")
        suffix = f": {e.achievements[0]}" if e.achievements else ""
        exp_lines.append(f"- {e.company} ({e.role}, {start} — {end}){suffix}")

    sections: list[str] = []
    if header_lines:
        sections.append("\n".join(header_lines))
    if skills_lines:
        sections.append("Стек:\n" + "\n".join(skills_lines))
    if exp_lines:
        sections.append("Опыт работы:\n" + "\n".join(exp_lines))
    if profile.free_preferences:
        sections.append("Дополнительно:\n" + profile.free_preferences.strip())
    return "\n\n".join(sections)
