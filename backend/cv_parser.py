import json
import logging
import re
from dataclasses import dataclass
from datetime import date

import httpx

from adapters.lm_studio import ChatRequest, chat
from backend.domain.taxonomy import CEFR_LEVELS, GRADES, WORK_FORMATS
from backend.llm.answers import QUOTE_TRANSLATION, str_or_none


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedCvProfile:
    first_name: str
    last_name: str
    title: str
    email: str
    phone: str | None
    location: str | None
    telegram_username: str | None
    github_url: str | None
    education: str | None
    work_format: list[str]
    grades: list[str]
    free_preferences: str | None


@dataclass(frozen=True)
class ParsedCvLanguage:
    language: str
    level: str


@dataclass(frozen=True)
class ParsedCvSkill:
    category: str
    name: str
    level: int
    aliases: list[str]


@dataclass(frozen=True)
class ParsedCvExperience:
    company: str
    company_url: str | None
    role: str
    start_date: date
    end_date: date | None
    achievements: list[str]
    responsibilities: list[str]
    stack: list[str]


@dataclass(frozen=True)
class ParsedCv:
    profile: ParsedCvProfile
    languages: list[ParsedCvLanguage]
    skills: list[ParsedCvSkill]
    experience: list[ParsedCvExperience]


# NOTE — known limitations of single-pass CV parsing.
#
# Эта функция остаётся one-shot LLM call'ом, и на локальной модели среднего
# размера упирается в её способность удержать длинный CV «в голове». В UI
# опция «Разобрать через LLM» отключена — парсинг помечен как «в разработке».
# Что наблюдалось на реальных резюме (фиксируем, чтобы вернуться позже):
#
#  - Перемешивание буллетов между местами работы. Модель приписывает
#    обязанности/достижения одной работы соседней работе, особенно когда
#    блоки идут подряд и шапки следуют близко друг к другу. Текущий промпт
#    содержит явное правило о «строгих границах работы», но модель его
#    стабильно нарушает на длинных CV.
#  - Дублирование одних и тех же буллетов в разных работах сразу.
#  - Путаница achievements ↔ responsibilities. Даже когда CV явно делит
#    блок на «Достижения:» и «Обязанности:», модель нередко скатывается на
#    тон буллета и кладёт «Сократил X» в achievements, даже если в
#    исходнике буллет напечатан под «Обязанности».
#  - Неполный/неверный stack у работы. В per-job stack попадают чужие
#    технологии (из общего скил-листа кандидата) или, наоборот, теряются
#    реальные элементы из секции «Стек:» этой работы. С другой стороны,
#    бывает, что модель «дорисовывает» весь канонический список в одну
#    работу.
#  - Неполный/неверный list of skills. Модель упускает технологии, явно
#    упомянутые в CV (включая язык, в честь которого названа категория —
#    «Python», «Java» и т.п. как заголовок раздела с подсписком).
#  - Дубли в aliases с самим name и между алиасами. Частично страхуется
#    кодом в _parse_skill, но первичная проблема в выходе модели.
#  - Галлюцинация имени работодателя. Слова-заглушки типа «Стартап»,
#    «Freelance», «NDA» модель «помогает» заменить на должность кандидата
#    или продукт. Промпт явно это запрещает, но рецидивы остаются.
#  - Потери на длинных CV. После усечения text[:20000] часть опыта может
#    остаться за пределами окна — связи скилов и буллетов из этих работ
#    теряются молча.
#
# Пробовали split на 4-проходный pipeline (см. историю git, ветка не
# мёрджилась): отдельный splitter, отдельный bullets-pass per work,
# отдельный skill-matching per work. На той же локальной модели стало
# хуже: splitter копировал raw_block_text неверно, skill-matcher
# галлюцинировал весь канонический список в одну работу. Возврат к
# single-pass и отключение фичи в UI — намеренное решение.
PARSE_CV_PROMPT = """Ты парсишь CV специалиста и извлекаешь структурированные данные в JSON.

На вход — полный текст резюме (markdown или plain text). На выход — ТОЛЬКО валидный JSON-объект следующей формы:
{
  "profile": {
    "first_name": "string",
    "last_name": "string",
    "title": "string",
    "email": "string",
    "phone": "string | null",
    "location": "string | null",
    "telegram_username": "string | null",
    "github_url": "string | null",
    "education": "string | null",
    "work_format": ["remote" | "hybrid" | "office", ...],
    "grades": ["junior" | "middle" | "senior" | "lead", ...],
    "free_preferences": "string | null"
  },
  "languages": [
    {"language": "string", "level": "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "native"}
  ],
  "skills": [
    {"category": "string", "name": "string", "level": 1-5, "aliases": ["string", ...]}
  ],
  "experience": [
    {
      "company": "string",
      "company_url": "string | null",
      "role": "string",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD | null",
      "achievements": ["string", ...],
      "responsibilities": ["string", ...],
      "stack": ["string", ...]
    }
  ]
}

Семантика profile:
- title: целевая должность / роль одной строкой, как кандидат позиционирует себя («Frontend Developer», «UX/UI дизайнер», «Marketing Lead», «Главный флорист», «Электрик-монтажник»). Без названия компании. Если в тексте только заголовок резюме — возьми его сюда (без лишних префиксов вроде «Резюме:»).
- first_name / last_name: имя и фамилия. Отчество в имя НЕ включай.
- email: email одной строкой.
- phone: телефон как написан, либо null.
- location: город/страна как написано в CV («Берлин, Германия», «Lisbon, Portugal», «Buenos Aires, Argentina», «Ереван, Армения»), либо null.
- telegram_username: только @username (без t.me/ и без https://). Если в тексте "https://t.me/foobar" — верни "@foobar".
- github_url: полный https-URL на github-профиль. Хвостовые "?tab=..." можно срезать.
- education: одна строка вида "ВУЗ, специальность, степень, год", если есть.
- work_format: подмножество из remote / hybrid / office — формат работы, который кандидат рассматривает или предпочитает, ЕСЛИ это явно сказано в CV («удалёнка», «гибрид», «офис», «remote», «хочу работать из дома»). Не угадывай из контекста. [] если не указано.
- grades: подмножество из junior / middle / senior / lead — только если уровень явно указан для кандидата (middle+, senior, «рассматриваю senior роли», team lead). НЕ выводи грейд из числа лет опыта. Многие нетехнические CV вообще не используют эти маркеры (используют «опытный», «ведущий», «главный», «помощник» и т.п.) — в таком случае верни []. [] если не указано или формулировки не маппятся в этот enum.
- free_preferences: краткое свободное текстовое поле с пожеланиями к вакансиям из блоков «О себе», «Цели», «Что ищу», «Обо мне», если там есть именно предпочтения по работе; иначе null. Не дублируй дословно весь раздел — сожми до сути.

Семантика languages:
- Уровень — строго CEFR (A1–C2) или native для родного языка. Название языка — в форме как в CV («Русский», «English», «Deutsch», «Français», «中文», «Português»). Пустой [], если языков нет в тексте.

Семантика skills:
- Извлекай навыки ИЗ ВСЕГО ТЕКСТА РЕЗЮМЕ, а не только из явного раздела «Профессиональные навыки» / «Skills» / «Технологии». Сканируй также: описания опыта работы, буллеты обязанностей/достижений, строки «Стек:» / «Tech stack:» внутри каждой работы, заголовок резюме (title), раздел «О себе». Если в CV нет отдельного блока скилов — собери список из упоминаний по всему тексту. Если технология встречается ТОЛЬКО в одном месте работы и нигде больше — она всё равно должна попасть в skills.
- Дедуплицируй: один и тот же навык / инструмент — ровно одна запись skills. Разные написания одного навыка («Postgres» и «PostgreSQL», «JS» и «JavaScript», «Photoshop» и «Adobe Photoshop» и «PS», «Figma» и «figma.com») — это ОДНА запись: каноническое имя в name, остальные написания — в aliases. Не создавай две записи для одного и того же.
- Каждый отдельный навык — отдельная запись JSON-массива. Если в исходной строке навыки перечислены через "|" / "," / "/" — раздели их на отдельные элементы.
- category: бери из заголовка списка в резюме ("Python", "Базы данных", "DevOps", "Дизайн", "Маркетинг", "Финансы", "Кулинария", "Языки", "Soft" и т.п.). Если категории нет — "Общее".
- name: канонизированное название навыка / инструмента / технологии ("Django", "PostgreSQL", "Apache Kafka", "Docker", "Figma", "InDesign", "HubSpot", "AutoCAD", "Прототипирование"). Без описаний.
- Если в CV целый блок навыков назван в честь самого языка / платформы / линейки продуктов (например, заголовок «Python», «JavaScript» с подсписком фреймворков; или «Adobe Suite» с подсписком Photoshop / Illustrator / InDesign), то и эта платформа/линейка сама тоже должна быть отдельным skill'ом — НЕ теряй её только потому, что она вынесена в заголовок категории. Положи её либо в подходящую категорию («Языки программирования», «Дизайн-инструменты»), либо в ту же категорию, если другой подходящей нет.
- level: целое 1-5, твоя оценка глубины владения по тексту CV. Опирайся на: упоминается ли в текущей работе, как часто встречается в опыте, как давно используется. Базовый ориентир: 5 — стержневой навык в текущей работе и большинстве опыта; 4 — регулярно используется; 3 — есть опыт, но не основной; 2 — был эпизодически; 1 — упоминание без явного опыта. НЕ ставь всем 3 — различай. Если по тексту невозможно сделать никакой обоснованной оценки (навык лишь в общем списке без контекста) — верни null, парсер подставит нейтральное значение.
- aliases: распространённые альтернативные написания ("PostgreSQL" → ["Postgres"], "JavaScript" → ["JS"], "Docker-Compose" → ["docker compose"], "Photoshop" → ["Adobe Photoshop", "PS"], "Figma" → ["figma.com"]). НЕ включай в aliases само значение name (даже в другом регистре) — алиас по определению ОТЛИЧАЕТСЯ от name. Не дублируй один и тот же вариант. [] если других реальных написаний нет.

Семантика experience:
- Один объект на одно место работы. Сохраняй порядок как в CV (обычно от свежего к старому).
- ГРАНИЦЫ РАБОТЫ строгие: каждый буллет (в achievements и responsibilities) и каждая запись в stack принадлежит ИСКЛЮЧИТЕЛЬНО той работе, под шапкой которой (название компании / должность / даты) он напечатан в CV. Граница места работы — от шапки этой работы до шапки следующей работы (или до конца раздела опыта). НИКОГДА не переноси буллеты, достижения, обязанности или элементы стека из одной работы в другую — даже если по смыслу они туда «лучше подходят». Если в исходном CV буллет напечатан между шапками работ A и B — он принадлежит работе A (та, что выше). Перед тем как добавить буллет в работу X, проверь, что в CV этот буллет действительно стоит между шапкой X и шапкой следующей работы.
- company: дословная подстрока из CV — название работодателя ровно так, как напечатано над описанием места работы, без URL и без описаний. Если в CV написано «Стартап», «Freelance», «NDA», «Частный проект», «Самозанятый», «Self-employed», «—» — клади ровно это слово. Никогда не заменяй название на должность кандидата, продукт, домен, технологию или «более понятный» вариант, даже если оригинал кажется слишком общим.
- company_url: URL компании, если указан рядом с названием. Иначе null.
- role: должность как в CV ("Frontend Developer", "UX/UI Designer", "Marketing Lead", "Главный флорист", "Backend разработчик").
- start_date / end_date: ISO YYYY-MM-DD. Месяц без числа → первое число месяца («Февраль 2025» → "2025-02-01"; «Feb 2025» → "2025-02-01"; «Februar 2025» → "2025-02-01"). Только год без месяца → "YYYY-01-01". "настоящее время" / "present" / "current" / "по сей день" → end_date: null.
- achievements и responsibilities — РАЗНЫЕ массивы. Ведро для буллета выбирается в одном из двух режимов.
  Режим A — у этой работы в CV есть хоть один явный заголовок-разделитель буллетов («Обязанности», «Функции», «Задачи», «Что делал», «Достижения», «Результаты», «Key achievements», «Impact», «Highlights», «Accomplishments» и т.п.). Тогда:
    - под achievement-заголовками («Достижения», «Результаты», «Key achievements», «Achievements», «Impact», «Highlights», «Accomplishments») → клади буллет в achievements.
    - под любым другим заголовком («Обязанности», «Функции», «Задачи», «Что делал», «Responsibilities», «Duties» и т.п.) → клади буллет в responsibilities.
    - Заголовок главнее тона буллета. Если буллет под «Обязанности» звучит как достижение — он ВСЁ РАВНО responsibility, потому что напечатан в этом разделе.
    - Если в CV есть только один из блоков (только «Обязанности» или только «Достижения») — второй массив оставь []. Не выдумывай второй список из тех же буллетов.
  Режим B — заголовков-разделителей у этой работы вообще нет (буллеты идут сплошным списком сразу под названием работы). Тогда классифицируй по тону каждого буллета:
    - явный измеримый/конкретный результат, метрика, «сократил X на N%», «внедрил Y», «запустил Z» → achievements.
    - рутинная функция, постоянная зона ответственности, «отвечал за», «разрабатывал», «поддерживал», «занимался» → responsibilities.
  Никогда не смешивай режимы: если хоть один заголовок есть — действует Режим A для всех буллетов работы.
  Каждый буллет — отдельная строка массива. Срезай ведущие "- ", "• ", "* ". Не дублируй и не объединяй буллеты.
- stack: массив конкретных навыков, инструментов или программ из секции "Стек" / "Tech stack" / "Технологии" / "Инструменты" / "Tools" этого опыта. Раздели по "|" / "," / "/". Без описаний. НЕ клади сюда категории/рубрики («Базы данных», «DevOps», «Языки программирования», «Frontend», «Дизайн-инструменты», «Маркетинговые инструменты», «Финансовые инструменты») — даже если в CV они там перечислены как заголовки.

Общие правила:
- Бери только то, что есть в тексте. Не выдумывай.
- Имена собственные (company, role, first_name, last_name) — только дословно копируй из CV. Не заменяй их на синонимы, описания или «более понятные» варианты, даже если оригинал кажется заглушкой или слишком общим словом.
- Если поля profile нет в CV — null (но first_name, last_name, title и email обязательны).
- languages, skills и experience могут быть пустыми массивами, если в CV их нет.
- Никакого текста вне JSON. Никакого markdown-обрамления. Никаких code-fence заборчиков. Никаких комментариев."""


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [s.strip() for s in value if isinstance(s, str) and s.strip()]


def _normalize_enum_list(raw: object, allowed: tuple[str, ...]) -> list[str]:
    """Значения из ответа модели, оставленные по справочнику: не строки и
    незнакомое отброшены, повторы сведены, порядок исходный.
    """
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        v = item.strip().lower()
        if v in allowed and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _normalize_lang_level(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    vl = v.lower()
    if vl in ("native", "родной"):
        return "native"
    up = v.upper()
    if up in CEFR_LEVELS:
        return up
    return None


def _parse_language_item(item) -> ParsedCvLanguage | None:
    if not isinstance(item, dict):
        return None
    language = str_or_none(item.get("language"))
    if not language:
        return None
    level = _normalize_lang_level(item.get("level"))
    if level is None:
        return None
    return ParsedCvLanguage(language=language, level=level)


def _parse_languages(raw: object) -> list[ParsedCvLanguage]:
    if not isinstance(raw, list):
        return []
    out: list[ParsedCvLanguage] = []
    seen: set[str] = set()
    for it in raw:
        row = _parse_language_item(it)
        if row is None:
            continue
        key = row.language.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


_YEAR_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")
_YEAR_RE = re.compile(r"^(\d{4})$")


def _parse_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        pass
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


def _parse_profile(data: dict) -> ParsedCvProfile | None:
    if not isinstance(data, dict):
        return None
    first_name = str_or_none(data.get("first_name"))
    last_name = str_or_none(data.get("last_name"))
    title = str_or_none(data.get("title"))
    email = str_or_none(data.get("email"))
    if not (first_name and last_name and title and email):
        return None
    return ParsedCvProfile(
        first_name=first_name,
        last_name=last_name,
        title=title,
        email=email,
        phone=str_or_none(data.get("phone")),
        location=str_or_none(data.get("location")),
        telegram_username=str_or_none(data.get("telegram_username")),
        github_url=str_or_none(data.get("github_url")),
        education=str_or_none(data.get("education")),
        work_format=_normalize_enum_list(data.get("work_format"), WORK_FORMATS),
        grades=_normalize_enum_list(data.get("grades"), GRADES),
        free_preferences=str_or_none(data.get("free_preferences")),
    )


def _parse_skill(item) -> ParsedCvSkill | None:
    if not isinstance(item, dict):
        return None
    category = str_or_none(item.get("category")) or "Общее"
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
    seen: set[str] = {name.casefold()}
    aliases: list[str] = []
    for a in _str_list(item.get("aliases")):
        key = a.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(a)
    return ParsedCvSkill(
        category=category,
        name=name,
        level=level,
        aliases=aliases,
    )


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
        achievements=_str_list(item.get("achievements")),
        responsibilities=_str_list(item.get("responsibilities")),
        stack=_str_list(item.get("stack")),
    )


def _parse_cv_json(answer: str) -> ParsedCv | None:
    cleaned = answer.translate(QUOTE_TRANSLATION)
    match = _JSON_OBJECT_RE.search(cleaned)
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    profile = _parse_profile(data.get("profile"))
    if profile is None:
        return None

    languages = _parse_languages(data.get("languages"))

    raw_skills = data.get("skills") if isinstance(data.get("skills"), list) else []
    skills = [s for s in (_parse_skill(it) for it in raw_skills) if s is not None]

    raw_exp = data.get("experience") if isinstance(data.get("experience"), list) else []
    experience = [
        e for e in (_parse_experience(it) for it in raw_exp) if e is not None
    ]

    return ParsedCv(
        profile=profile,
        languages=languages,
        skills=skills,
        experience=experience,
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
                {"role": "user", "content": text},
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
    finish_reason = reply.finish_reason

    if finish_reason == "length":
        logger.warning("parse_cv: LLM hit token limit, output may be truncated")

    parsed = _parse_cv_json(answer)
    if parsed is None:
        logger.warning("parse_cv: LLM returned unparseable output %r", answer[:300])
    return parsed
