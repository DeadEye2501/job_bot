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
from backend.domain.skill_names import skill_key
from backend.domain.spellings import dedupe_first_wins
from backend.domain.taxonomy import (
    GRADES,
    LEVEL_WHEN_UNTOLD,
    LEVELS_BY_SPELLING,
    NATIVE_LEVEL,
    WORK_FORMATS,
)
from backend.domain.wording import spelled_alone
from backend.incoming import fold_homoglyphs, normalize_enum_list, str_list
from backend.llm.answers import (
    ONLY_JSON,
    json_object,
    log_unparseable,
    str_or_none,
)
from backend.llm.cv_grounding import grounded_in_cv
from backend.llm.cv_native import with_native_language
from backend.llm.external import external_block
from backend.llm.rules import NOT_A_SKILL_LINE, NOT_A_SKILL_SECTIONS
from backend.payloads import (
    REQUIRED_PROFILE_FIELDS,
    ParsedCv,
    ParsedCvExperience,
    ParsedCvLanguage,
    ParsedCvProfile,
    ParsedCvSkill,
)


logger = logging.getLogger(__name__)


# Чего ждать от разбора и почему он устроен в один заход.
#
# Один заход держит и слабая местная модель: четыре страницы она разбирает
# минутой с небольшим, не путая буллеты между работами, — при условии что
# текст пришёл в порядке чтения, о чём заботится `adapters/cv_text.py`.
# Многопроходный разбор — splitter, разбор буллетов по работам, сличение
# навыков — на той же модели выходит хуже: splitter копирует куски неверно.
#
# Что остаётся кривым:
#  - Мелкие поля-перечисления модель выдумывает: грейд выводит из стажа, формат
#    работы — из графика, язык — из страны проживания. Запретами в промпте это
#    лечится наполовину, поэтому все они сверяются с текстом резюме в
#    `cv_grounding.py`.
#  - Уровень языка, названный словом, переводится в шкалу
#    (`domain/taxonomy.LEVEL_SPELLINGS`); названный невнятно — «технический»,
#    «письменный» — заменяется высшим. Уровня не называет тот, кто в языке
#    уверен, и низший на его месте отрезал бы такому человеку все вакансии,
#    где язык нужен.
#  - Модель тянет в стек работы то, что названо в её обязанностях, и общий
#    список навыков кандидата заодно. Сверка снимает это, спрашивая заголовок
#    над стеком, а не сами названия — они-то настоящие. Остаётся щель: у
#    последней работы кусок текста тянется до конца резюме, и раздел «Технологии»
#    в хвосте она примет за свой.
#  - Язык, названный не в разделе языков, а строкой внутри профессиональных
#    навыков («Английский язык — Advanced/C1»), слабая модель теряет вовсе.
#    Подсказка в наставлении этого не лечит; сильная модель находит его и без
#    подсказки.
#  - Длинное резюме режется по `text[:20000]`, и остаток теряется молча.
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
    "work_format": [""" + " | ".join(f'"{one}"' for one in WORK_FORMATS) + """, ...],
    "grades": [""" + " | ".join(f'"{one}"' for one in GRADES) + """, ...],
    "free_preferences": "string | null"
  },
  "languages": [
    {"language": "string", "level": "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "native" | "слово из резюме" | null}
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
- first_name / last_name: имя и фамилия. Отчество в имя НЕ включай. Набранное в шапке резюме заглавными («ИВАН ПЕТРОВ») верни обычным письмом: «Иван», «Петров».
- email: email одной строкой.
- phone: телефон как написан, либо null.
- location: город/страна как написано в CV («Берлин, Германия», «Lisbon, Portugal», «Buenos Aires, Argentina», «Тверь, Тверская область»), либо null.
- telegram_username: только @username (без t.me/ и без https://). Если в тексте "https://t.me/foobar" — верни "@foobar".
- github_url: полный https-URL на github-профиль. Хвостовые "?tab=..." можно срезать.
- education: одна строка вида "ВУЗ, специальность, степень, год", если есть.
- work_format: подмножество из """ + " / ".join(WORK_FORMATS) + """ — формат работы, который кандидат рассматривает или предпочитает, ЕСЛИ это явно сказано в CV («удалёнка», «гибрид», «офис», «remote», «хочу работать из дома»). Не угадывай из контекста. [] если не указано.
- grades: подмножество из """ + " / ".join(GRADES) + """ — только если кандидат САМ называет свой уровень: «Senior Python Developer» в заголовке резюме, «middle+», «рассматриваю senior роли», «ищу позицию тимлида». Ничего не выводи ни из стажа, ни из числа мест работы, ни из объёма ответственности, ни из названия прошлой должности: «Team-lead» в шапке места работы — это кем человек РАБОТАЛ, а не то, кем он себя объявляет. Многие нетехнические CV вообще не используют эти маркеры (используют «опытный», «ведущий», «главный», «помощник» и т.п.) — в таком случае верни []. Сомневаешься — верни []: пустой список честнее выдуманного грейда, по грейду отбирают вакансии.
- free_preferences: краткое свободное текстовое поле с пожеланиями к вакансиям из блоков «О себе», «Цели», «Что ищу», «Обо мне», если там есть именно предпочтения по работе; иначе null. Не дублируй дословно весь раздел — сожми до сути.

Семантика languages:
- Название языка — в форме как в CV («Русский», «English», «Deutsch», «Français», «中文», «Português»).
- Язык, на котором написано САМО резюме, — родной: верни его с level "native" всегда, даже если раздела языков в резюме нет и слово «русский» («English», «Deutsch») в тексте не встречается ни разу.
- Остальные языки берутся ТОЛЬКО из текста. Не добавляй язык по национальности имени или по стране проживания.
- Уровень тоже берётся только из текста, и переписывается как есть. Назван по шкале — верни по шкале. Назван словом («свободно», «разговорный», «базовый», «fluent», «в совершенстве») — верни ЭТО СЛОВО, а не свою догадку о том, какой шкале оно отвечает. Не назван вовсе — верни level: null.

Семантика skills:
- Извлекай навыки ИЗ ВСЕГО ТЕКСТА РЕЗЮМЕ, а не только из явного раздела «Профессиональные навыки» / «Skills» / «Технологии». Сканируй также: описания опыта работы, буллеты обязанностей/достижений, строки «Стек:» / «Tech stack:» внутри каждой работы, заголовок резюме (title), раздел «О себе». Если в CV нет отдельного блока скилов — собери список из упоминаний по всему тексту. Если технология встречается ТОЛЬКО в одном месте работы и нигде больше — она всё равно должна попасть в skills.
- Дедуплицируй: один и тот же навык / инструмент — ровно одна запись skills. Разные написания одного навыка («Postgres» и «PostgreSQL», «JS» и «JavaScript», «Photoshop» и «Adobe Photoshop» и «PS», «Figma» и «figma.com») — это ОДНА запись: каноническое имя в name, остальные написания — в aliases. Не создавай две записи для одного и того же.
- Каждый отдельный навык — отдельная запись JSON-массива. Если в исходной строке навыки перечислены через "|" / "," / "/" — раздели их на отдельные элементы.
- category: бери из заголовка списка в резюме ("Python", "Базы данных", "DevOps", "Дизайн", "Маркетинг", "Финансы", "Кулинария" и т.п.). Если категории нет — "Общее". Заголовок пиши тот, что стоит в резюме, — по нему видно, откуда навык взят.
- name: канонизированное название навыка / инструмента / технологии ("Django", "PostgreSQL", "Apache Kafka", "Docker", "Figma", "InDesign", "HubSpot", "AutoCAD", "Прототипирование"). Без описаний.
- Навыком НЕ считаются и в skills не попадают: водительские права и категории; знание языков — для них есть свой массив languages; семейное положение, готовность к переезду и командировкам.
- Личные качества — тоже не навык, НА ЛЮБОМ ЯЗЫКЕ. Это свойства характера и общие способности, а не инструменты и не предметные умения: «ответственность», «внимательность», «стрессоустойчивость», «коммуникабельность», «работа в команде», «обучаемость», «Creative Thinking», «Communication», «Time Management», «Team Player», «Problem Solving», «Leadership», «Research», «Attention to detail». Целый раздел, названный так — """ + NOT_A_SKILL_LINE + """, — в skills не переносится ВООБЩЕ, ни одной записью, как бы он ни назывался.
- Если в CV целый блок навыков назван в честь самого языка / платформы / линейки продуктов (например, заголовок «Python», «JavaScript» с подсписком фреймворков; или «Adobe Suite» с подсписком Photoshop / Illustrator / InDesign), то и эта платформа/линейка сама тоже должна быть отдельным skill'ом — НЕ теряй её только потому, что она вынесена в заголовок категории. Положи её либо в подходящую категорию («Языки программирования», «Дизайн-инструменты»), либо в ту же категорию, если другой подходящей нет.
- level: целое 1-5, твоя оценка глубины владения по тексту CV. Опирайся на: упоминается ли в текущей работе, как часто встречается в опыте, как давно используется. Базовый ориентир: 5 — стержневой навык в текущей работе и большинстве опыта; 4 — регулярно используется; 3 — есть опыт, но не основной; 2 — был эпизодически; 1 — упоминание без явного опыта. НЕ ставь всем 3 — различай. Если по тексту невозможно сделать никакой обоснованной оценки (навык лишь в общем списке без контекста) — верни null, парсер подставит нейтральное значение.
- aliases: распространённые альтернативные написания ("PostgreSQL" → ["Postgres"], "JavaScript" → ["JS"], "Docker-Compose" → ["docker compose"], "Photoshop" → ["Adobe Photoshop", "PS"], "Figma" → ["figma.com"]). НЕ включай в aliases само значение name (даже в другом регистре) — алиас по определению ОТЛИЧАЕТСЯ от name. Не дублируй один и тот же вариант. [] если других реальных написаний нет.

Семантика experience:
- Один объект на одно место работы. Сохраняй порядок как в CV (обычно от свежего к старому).
- ГРАНИЦЫ РАБОТЫ строгие: каждый буллет (в achievements и responsibilities) и каждая запись в stack принадлежит ИСКЛЮЧИТЕЛЬНО той работе, под шапкой которой (название компании / должность / даты) он напечатан в CV. Граница места работы — от шапки этой работы до шапки следующей работы (или до конца раздела опыта). НИКОГДА не переноси буллеты, достижения, обязанности или элементы стека из одной работы в другую — даже если по смыслу они туда «лучше подходят». Если в исходном CV буллет напечатан между шапками работ A и B — он принадлежит работе A (та, что выше). Перед тем как добавить буллет в работу X, проверь, что в CV этот буллет действительно стоит между шапкой X и шапкой следующей работы.
- company: дословная подстрока из CV — название работодателя ровно так, как напечатано над описанием места работы, без URL и без описаний. Если в CV написано «Стартап», «Freelance», «NDA», «Частный проект», «Самозанятый», «Self-employed», «—» — клади ровно это слово. Никогда не заменяй название на должность кандидата, продукт, домен, технологию или «более понятный» вариант, даже если оригинал кажется слишком общим.
- company_url: URL компании, если указан рядом с названием. Иначе null.
- role: должность как в CV ("Frontend Developer", "UX/UI Designer", "Marketing Lead", "Главный флорист", "Backend разработчик").
- start_date / end_date: ISO YYYY-MM-DD. Месяц без числа → ПЕРВОЕ число месяца, и это правило одинаково для обеих дат: «Февраль 2025» → "2025-02-01"; «Feb 2025» → "2025-02-01"; «Februar 2025» → "2025-02-01"; «Апрель 2015 — сентябрь 2022» → start_date "2015-04-01", end_date "2022-09-01". Последним числом месяца дату окончания НЕ ставь: «сентябрь 2022» — это "2022-09-01", а не "2022-09-30". Только год без месяца → "YYYY-01-01". "настоящее время" / "present" / "current" / "по сей день" → end_date: null.
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
- stack: массив конкретных навыков, инструментов или программ из секции "Стек" / "Tech stack" / "Технологии" / "Инструменты" / "Tools" этого опыта. Раздели по "|" / "," / "/". Без описаний. Нет у этой работы такой секции — верни []: не собирай стек пересказом обязанностей («электрические сети», «монтажные работы» — это работа, а не инструмент) и не переноси сюда общий список навыков кандидата из раздела «Профессиональные навыки». Пустой stack — нормальный ответ, у нетехнических работ его не бывает вовсе. НЕ клади сюда категории/рубрики («Базы данных», «DevOps», «Языки программирования», «Frontend», «Дизайн-инструменты», «Маркетинговые инструменты», «Финансовые инструменты») — даже если в CV они там перечислены как заголовки.

Общие правила:
- Бери только то, что есть в тексте. Не выдумывай.
- Имена собственные (company, role, first_name, last_name) — только дословно копируй из CV. Не заменяй их на синонимы, описания или «более понятные» варианты, даже если оригинал кажется заглушкой или слишком общим словом.
- Если поля profile нет в CV — null (но first_name, last_name, title и email обязательны).
- languages, skills и experience могут быть пустыми массивами, если в CV их нет.
- """ + ONLY_JSON


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
    if plain in (NATIVE_LEVEL, "родной"):
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
    if not isinstance(raw, list):
        return []
    best: dict[str, tuple[str, str | None]] = {}
    for row in (_parse_language_item(it) for it in raw):
        if row is None:
            continue
        language, level = row
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
    v = str_or_none(value)
    if v is None:
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
        achievements=str_list(item.get("achievements")),
        responsibilities=str_list(item.get("responsibilities")),
        stack=str_list(item.get("stack")),
    )


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
    return with_native_language(grounded_in_cv(parsed, text), text)
