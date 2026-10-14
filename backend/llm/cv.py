"""Разбор резюме моделью: из текста файла — заполненная анкета.

Сосед по слою — `llm/vacancy.py`, и устройство у них одно: собрать запрос,
спросить модель, разобрать ответ, привести поля к нашим справочникам. Отличает
предмет: там объявление, которое читают, здесь резюме, которое пишут.

Разобранные значения живут в `backend/payloads.py` рядом с прочими: собирает их
разбор, а читают анкета и окно.
"""

import logging
import re
from datetime import date

import httpx

from adapters.lm_chat import ChatRequest, chat
from backend.domain.sentence import closed_sentence
from backend.domain.skill_names import skill_key
from backend.domain.spellings import dedupe_first_wins
from backend.domain.taxonomy import (
    GRADES,
    LEVEL_WHEN_UNTOLD,
    LEVELS_BY_SPELLING,
    NATIVE_LEVEL,
    NATIVE_SPELLINGS,
    WORK_FORMATS,
)
from backend.domain.wording import spelled_alone
from backend.domain.salary import currency_sign
from backend.incoming import (
    amount_or_none,
    enum_member_or_none,
    fold_homoglyphs,
    normalize_enum_list,
    str_list,
)
from backend.llm.answers import (
    json_object,
    log_unparseable,
    str_or_none,
)
from backend.llm.cv_grounding import grounded_in_cv
from backend.llm.cv_native import with_native_language
from backend.llm.cv_prompt import PARSE_CV_PROMPT
from backend.llm.external import external_block
from backend.llm.rules import NOT_A_SKILL_SECTIONS
from backend.models import Gender, SalaryPeriod
from backend.payloads import (
    REQUIRED_PROFILE_FIELDS,
    ParsedCv,
    ParsedCvExperience,
    ParsedCvLanguage,
    ParsedCvProfile,
    ParsedCvProject,
    ParsedCvSkill,
)


logger = logging.getLogger(__name__)


def _normalize_lang_level(value: object) -> str | None:
    """Уровень по шкале; пусто — сказанного не понять.

    Слово вместо шкалы переводится, а не приравнивается к нижнему уровню:
    «свободно» — это названный уровень, просто не по шкале, и считать его
    начальным значило бы отрезать человеку все вакансии, где язык нужен.
    """
    v = str_or_none(value)
    if v is None:
        return None
    # Промпт просит вернуть уровень как в резюме, а там его пишут по-всякому:
    # «Свободно.», «C1 (advanced)», «Upper Intermediate». Дефис и пробел
    # сводятся к одному, обрамление отбрасывается.
    plain = re.sub(r"[\s\-]+", " ", v.strip().strip(".,;:()").lower())
    if plain in NATIVE_SPELLINGS:
        return NATIVE_LEVEL
    # Обозначение шкалы ищется по сведённой строке, а слово — по исходной:
    # сведение выручает «В2» русскими буквами и оно же портит «свободно».
    by_scale = re.search(r"\b([abc][12])\b", fold_homoglyphs(plain))
    if by_scale is not None:
        return by_scale.group(1).upper()
    for spelling, level in LEVELS_BY_SPELLING:
        if spelled_alone(plain, spelling):
            return level
    return None


def _parse_language_item(item) -> tuple[str, str | None] | None:
    """Название языка и его уровень; пусто — языка в записи нет.

    Неразобранный уровень отдаётся пустотой, а не заменяется умолчанием:
    подставленное неотличимо от названного, и при повторе языка оно затёрло бы
    настоящий уровень.
    """
    if not isinstance(item, dict):
        return None
    language = str_or_none(item.get("language"))
    if not language:
        return None
    return language, _normalize_lang_level(item.get("level"))


def _parse_languages(raw: object) -> list[ParsedCvLanguage]:
    """Языки анкеты: по одному на язык, уровень неизвестен — высший.

    Отбор повторов свой, а не общий `dedupe_first_wins`: первым здесь
    побеждает не всякий, а тот, у кого уровень назван. Модель присылает один
    и тот же язык дважды — «Английский: технический» и «Английский: C1», — и
    первым в списке чаще стоит невнятный.

    Уровень, оставшийся неизвестным, заменяется высшим: колонка обязательная,
    хранить «неизвестно» негде, а выбросить язык значило бы потерять названное
    человеком. Высшим, а не низшим, потому что уровня не называет тот, кто в
    языке уверен, — неуверенный как раз уточняет.
    """
    best: dict[str, tuple[str, str | None]] = {}
    for language, level in _parsed_items(raw, _parse_language_item):
        known = best.get(language.casefold())
        if known is not None and known[1] is not None:
            continue
        best[language.casefold()] = (known[0] if known else language, level)
    return [
        ParsedCvLanguage(language=name, level=level or LEVEL_WHEN_UNTOLD)
        for name, level in best.values()
    ]


_YEAR_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")
_YEAR_RE = re.compile(r"^(\d{4})$")


def _parse_date(value) -> date | None:
    """Полная дата, а неполная — достроенная до первого числа: так пишут
    начало и конец работы."""
    full = _full_date(value)
    if full is not None:
        return full
    v = str_or_none(value)
    if v is None:
        return None
    m = _YEAR_MONTH_RE.match(v)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            return None
    m = _YEAR_RE.match(v)
    if m:
        try:
            return date(int(m.group(1)), 1, 1)
        except ValueError:
            return None
    return None


def _full_date(value) -> date | None:
    """Только полная дата; неполная — отсутствие, а не достроенный день.

    День рождения уходит в анкету на сайте от имени человека, и достроенный
    день был бы выдуманным.
    """
    v = str_or_none(value)
    if v is None:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def _parse_profile(data: dict) -> ParsedCvProfile | None:
    if not isinstance(data, dict):
        return None
    required = {name: str_or_none(data.get(name)) for name in REQUIRED_PROFILE_FIELDS}
    if not all(required.values()):
        return None
    return ParsedCvProfile(
        **required,
        phone=str_or_none(data.get("phone")),
        location=str_or_none(data.get("location")),
        telegram_username=str_or_none(data.get("telegram_username")),
        github_url=str_or_none(data.get("github_url")),
        education=str_or_none(data.get("education")),
        work_format=normalize_enum_list(data.get("work_format"), WORK_FORMATS),
        grades=normalize_enum_list(data.get("grades"), GRADES),
        free_preferences=str_or_none(data.get("free_preferences")),
        expected_salary=amount_or_none(data.get("expected_salary")),
        expected_salary_currency=currency_sign(
            str_or_none(data.get("expected_salary_currency"))
        ),
        expected_salary_period=enum_member_or_none(
            data.get("expected_salary_period"), SalaryPeriod
        ),
        first_name_latin=str_or_none(data.get("first_name_latin")),
        last_name_latin=str_or_none(data.get("last_name_latin")),
        gender=enum_member_or_none(data.get("gender"), Gender),
        patronymic=str_or_none(data.get("patronymic")),
        patronymic_latin=str_or_none(data.get("patronymic_latin")),
        birth_date=_full_date(data.get("birth_date")),
        citizenship=str_or_none(data.get("citizenship")),
        about_me=str_or_none(data.get("about_me")),
        resume_url=str_or_none(data.get("resume_url")),
    )


# Как в резюме называют раздел с личными качествами. Категорию модель берёт
# из заголовка над списком, и по нему такой раздел и опознаётся: запрет
# «качества — не навык» словами держится по-русски и рассыпается на английском
# «Soft Skills». А качества в навыках дороги: навык сличают со стеком
# вакансии, и «Communication» там не сличается ни с чем.
# Собирается из общего перечня: наставление и отсев обязаны знать одни и те же
# названия. Слово при этом ищется целым — «soft skill» подстрокой сидит внутри
# «Microsoft Skills», и бухгалтер лишился бы всего блока с Excel, Word и 1С.
# Хвост слова свободен: «Soft-скилы» и «софт-скилам» — один раздел.
_NOT_A_SKILL_SECTION_RE = re.compile(
    r"\b("
    + "|".join(
        r"[\s-]+".join(re.escape(part) for part in re.split(r"[\s-]+", one))
        for one in NOT_A_SKILL_SECTIONS
    )
    + r")\w*",
    re.IGNORECASE,
)


def _parse_skill(item) -> ParsedCvSkill | None:
    if not isinstance(item, dict):
        return None
    category = str_or_none(item.get("category")) or "Общее"
    if _NOT_A_SKILL_SECTION_RE.search(category):
        logger.info("разбор резюме: раздел %r навыком не считается", category)
        return None
    name = str_or_none(item.get("name"))
    if not name:
        return None
    raw_level = item.get("level")
    if raw_level is None or "level" not in item:
        level = 3
    elif isinstance(raw_level, bool):
        logger.warning("parse_cv: skill %r got boolean level %r, defaulting to 3", name, raw_level)
        level = 3
    elif isinstance(raw_level, (int, float)):
        level = int(raw_level)
    elif isinstance(raw_level, str) and raw_level.strip().lstrip("-").isdigit():
        level = int(raw_level.strip())
    else:
        logger.warning("parse_cv: skill %r got non-numeric level %r, defaulting to 3", name, raw_level)
        level = 3
    level = max(1, min(5, level))
    # Ключ тот же, что у сравнения навыков: иначе «Node.js» и «node js»
    # доезжали бы до анкеты двумя написаниями, там сталкивались по ключу, и
    # второе молча теряло бы привязку.
    return ParsedCvSkill(
        category=category,
        name=name,
        level=level,
        aliases=dedupe_first_wins(
            str_list(item.get("aliases")), skill_key, {skill_key(name)}
        ),
    )


def _points(value) -> list[str]:
    """Пункты перечня записи, каждый — законченной фразой с точкой.

    Резюме ставит точку то в одном пункте, то в другом, а пункт без неё
    выбивается из списка. Свой знак конца фразы остаётся — и за закрывающей
    кавычкой или скобкой тоже; точка с запятой, запятая и двоеточие уступают
    точке. Пункт из одних таких знаков пуст и выпадает.
    """
    points = [point.rstrip(";,: ") for point in str_list(value)]
    return [closed_sentence(point) for point in points if point]


def _parse_experience(item) -> ParsedCvExperience | None:
    if not isinstance(item, dict):
        return None
    company = str_or_none(item.get("company"))
    role = str_or_none(item.get("role"))
    start = _parse_date(item.get("start_date"))
    if not (company and role and start):
        return None
    return ParsedCvExperience(
        company=company,
        company_url=str_or_none(item.get("company_url")),
        role=role,
        start_date=start,
        end_date=_parse_date(item.get("end_date")),
        achievements=_points(item.get("achievements")),
        responsibilities=_points(item.get("responsibilities")),
        stack=str_list(item.get("stack")),
    )


def _parse_project(item) -> ParsedCvProject | None:
    """Проект из ответа модели; без названия — пусто."""
    if not isinstance(item, dict):
        return None
    name = str_or_none(item.get("name"))
    if not name:
        return None
    return ParsedCvProject(
        name=name,
        url=str_or_none(item.get("url")),
        about=_points(item.get("about")),
        stack=str_list(item.get("stack")),
    )


def _parsed_items(raw: object, parse) -> list:
    """Перечень из ответа модели: каждый элемент разобран, негодные отброшены;
    не перечень вовсе — пусто."""
    items = raw if isinstance(raw, list) else []
    return [one for one in (parse(item) for item in items) if one is not None]


def _parse_cv_json(answer: str) -> ParsedCv | None:
    """Разобранное резюме из ответа модели; пусто — разбирать нечего.

    Объект собирает общее объявление (`json_object`), а не своё тело: своё
    обошлось бы без записи в журнал, и неразобравшийся ответ пропадал бы молча.
    """
    data = json_object(answer, logger, "parse_cv")
    if data is None:
        return None

    profile = _parse_profile(data.get("profile"))
    if profile is None:
        return None

    return ParsedCv(
        profile=profile,
        languages=_parse_languages(data.get("languages")),
        skills=_parsed_items(data.get("skills"), _parse_skill),
        experience=_parsed_items(data.get("experience"), _parse_experience),
        projects=_parsed_items(data.get("projects"), _parse_project),
        text_language=str_or_none(data.get("text_language")),
    )


async def parse_cv(
    text: str,
    client: httpx.AsyncClient,
    model: str,
) -> ParsedCv | None:
    if not text or not text.strip():
        return None
    text = text[:20000]
    reply = await chat(
        client,
        model,
        ChatRequest(
            purpose="parse_cv",
            messages=[
                {"role": "system", "content": PARSE_CV_PROMPT},
                # Резюме своё, но рамка данных ставится и тут: шов один на все
                # обращения к модели, и исключений в нём быть не должно —
                # следующее заведут по образцу соседнего.
                {"role": "user", "content": external_block(text, "текст резюме")},
            ],
            max_tokens=4500,
            # Разбор резюме — одно тяжёлое обращение: слабая местная
            # модель считает его минутами, и общего запаса ей мало.
            timeout=300.0,
        ),
        logger,
    )
    if reply.text is None:
        return None
    answer = reply.text

    parsed = _parse_cv_json(answer)
    if parsed is None:
        log_unparseable(answer, logger, "parse_cv")
        return None
    return with_native_language(grounded_in_cv(parsed, text))
