"""Построение объектов, которые тесты подают на вход коду.

Здесь и полезные нагрузки, и строки моделей — но только то, что живёт в
памяти, без сессии. Настоящая запись в базу остаётся делом самих тестов —
фабрика не знает ни про сессию, ни про схему.
"""

from datetime import date, datetime, timedelta, timezone

from backend.runtime_settings import TgAccountConfig

from backend.models import (
    AppSetting,
    Blacklist,
    BotMode,
    BotState,
    Company,
    HR,
    LlmConfig,
    LlmConfigKind,
    Message,
    Profile,
    ProfileExperience,
    ProfileSkill,
    StatusHistorySource,
    TelegramChannel,
    TgAccount,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
    VacancyStatusHistory,
)
from backend.payloads import (
    ParsedCv,
    ParsedCvExperience,
    ParsedCvProfile,
    ParsedCvSkill,
    ParsedVacancy,
)

EPOCH = datetime(2026, 1, 1, 12, 0)
"""Опорный момент для строк, у которых порядок по времени и есть предмет проверки.

Наивный: колонки объявлены `DateTime(timezone=True)`, но SQLite хранит их без
зоны и возвращает наивными — смешивать с осведомлёнными нельзя, сравнение
упадёт с `TypeError`.
"""


def at(minutes: int) -> datetime:
    """Момент на `minutes` минут позже опорного."""
    return EPOCH + timedelta(minutes=minutes)


def days_ago(days: float) -> datetime:
    """Момент за `days` суток до сейчас, наивный по UTC.

    Нужен там, где проверяемый код сам смотрит на текущее время и отмеряет
    от него, — тогда опорный момент не годится: он лежит в прошлом на
    неизвестном расстоянии, и проверка зависела бы от дня прогона.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


_PHOTO_HEADS = {
    ".jpg": b"\xff\xd8\xff\xe0",
    ".jpeg": b"\xff\xd8\xff\xe0",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".webp": b"RIFF" + bytes(4) + b"WEBP",
}


def photo_head(suffix: str) -> bytes:
    """Начало настоящей картинки такого вида; для прочего — пусто.

    Выбор между картинкой и документом смотрит на содержимое, а не на имя,
    поэтому файлу с картиночным расширением нужна и картиночная подпись.
    """
    return _PHOTO_HEADS.get(suffix.lower(), b"")


def _empty_vacancy() -> dict:
    """Свежий словарь умолчаний на каждый вызов.

    `stack_required`/`stack_preferred` — списки, и общий на все вызовы
    словарь-константа отдавал бы один и тот же объект списка каждой
    построенной вакансии: мутация в одном тесте протекала бы в другой.
    Функция вместо константы гарантирует, что у двух вызовов подряд
    списки — разные объекты.
    """
    return {
        "title": "Python-разработчик",
        "description": None,
        "company_name": None,
        "company_website": None,
        "hr_contact": None,
        "other_contact": None,
        "stack_required": [],
        "stack_preferred": [],
        "grade": None,
        "salary": None,
        "remote": None,
        "location": None,
    }


def parsed_vacancy(**overrides) -> ParsedVacancy:
    """Разобранная вакансия: заголовок есть, остальное пусто.

    Умолчание выбрано так, чтобы тест называл ровно те поля, которые
    проверяет: всё незаданное заведомо не влияет на результат.
    """
    return ParsedVacancy(**{**_empty_vacancy(), **overrides})


def skill_fields(**overrides) -> dict:
    """Умолчания навыка — одни и на строку в базе, и на разобранный из резюме.

    Отдаются новым словарём на каждый зов: перечень прозвищ изменяем, и один
    список на все строки связал бы их между собой.
    """
    return {"category": "backend", "level": 3, "aliases": [], **overrides}


def parsed_cv_profile(**overrides) -> ParsedCvProfile:
    """Разобранный профиль: обязательное заполнено, остальное пусто.

    Тот же человек, что и в строке анкеты, — иначе проверка «разобранное легло
    в анкету» сравнивала бы двух разных.
    """
    fields = person_fields(
        phone=None,
        location=None,
        telegram_username=None,
        github_url=None,
        education=None,
        work_format=[],
        grades=[],
        free_preferences=None,
    )
    fields.update(overrides)
    return ParsedCvProfile(**fields)


def parsed_cv_skill(name: str, **overrides) -> ParsedCvSkill:
    """Разобранный навык — с теми же умолчаниями, что и строка в базе."""
    return ParsedCvSkill(name=name, **skill_fields(**overrides))


def parsed_cv_place(**overrides) -> ParsedCvExperience:
    """Разобранное место работы — с теми же умолчаниями, что и строка в базе.

    Своё поле здесь одно: стек места работы разбор из резюме приносит, а
    колонки под него нет.
    """
    fields = experience_fields(stack=[])
    fields.update(overrides)
    return ParsedCvExperience(**fields)


def parsed_cv(**overrides) -> ParsedCv:
    """Разобранное резюме целиком."""
    fields = {
        "profile": parsed_cv_profile(),
        "languages": [],
        "skills": [],
        "experience": [],
    }
    fields.update(overrides)
    return ParsedCv(**fields)


def profile_skill(
    name: str, level: int | None = None, aliases: list | None = None, **overrides
) -> ProfileSkill:
    """Навык профиля — и как вход в подсчёт, и как строка в базе."""
    fields = skill_fields(**overrides)
    if level is not None:
        fields["level"] = level
    if aliases is not None:
        fields["aliases"] = aliases
    return ProfileSkill(name=name, **fields)


def tg_account_row(**overrides) -> TgAccount:
    """Строка учётной записи Telegram. Шифротексты кладёт вызывающий.

    Таблица односрочная с проверкой `id = 1` на уровне базы, поэтому
    умолчание для идентификатора — 1, но переопределение сливается до
    вызова конструктора: `id=` в overrides проходит, а не падает сырым
    `TypeError` о повторном ключевом аргументе.
    """
    fields = {
        "id": 1,
        "api_id": 26276902,
        "api_hash_encrypted": None,
        "phone": "+70000000000",
        "password_encrypted": None,
        "session_blob_encrypted": None,
    }
    fields.update(overrides)
    return TgAccount(**fields)


def llm_config_row(kind: LlmConfigKind, **overrides) -> LlmConfig:
    """Строка настройки провайдера LLM. Род задаётся явно: он уникален."""
    fields = {
        "base_url": "http://provider.test",
        "api_key_encrypted": None,
        "model": "qwen",
    }
    fields.update(overrides)
    return LlmConfig(kind=kind, **fields)


def app_setting_row(key: str, value: str | None, **overrides) -> AppSetting:
    """Строка настройки в общем словаре ключ-значение."""
    fields = {"key": key, "value": value}
    fields.update(overrides)
    return AppSetting(**fields)


def bot_state_row(mode: BotMode) -> BotState:
    """Строка состояния бота. Тоже односрочная с проверкой `id = 1`."""
    return BotState(id=1, mode=mode)


def vacancy_row(**overrides) -> Vacancy:
    """Строка вакансии, годная к выдаче в список.

    `is_parsed` — True: `list_vacancies` отбрасывает неразобранные, и
    умолчание False заставляло бы каждый тест списка называть поле, к
    которому он не имеет отношения. Тест про сам отбор задаёт его явно.

    `created_at` задан, а не оставлен базе: у колонки серверное умолчание
    `CURRENT_TIMESTAMP`, и две строки, вставленные в одну секунду, получили
    бы одинаковую метку — порядок по времени стал бы делом случая.
    """
    fields = {
        "title": "Python-разработчик",
        "status": VacancyStatus.NEW,
        "is_parsed": True,
        "created_at": EPOCH,
    }
    fields.update(overrides)
    return Vacancy(**fields)


def hr_row(**overrides) -> HR:
    """Строка HR."""
    fields = {"name": "Мария", "telegram_username": "maria"}
    fields.update(overrides)
    return HR(**fields)


def company_row(**overrides) -> Company:
    """Строка компании. Имя уникально на уровне базы — задаётся явно."""
    fields = {"name": "Контур", "aliases": []}
    fields.update(overrides)
    return Company(**fields)


def channel_row(**overrides) -> TelegramChannel:
    """Строка канала-источника."""
    fields = {"username": "pyjobs", "title": "Питон-вакансии"}
    fields.update(overrides)
    return TelegramChannel(**fields)


def person_fields(**overrides) -> dict:
    """Кто такой подопытный кандидат — одно описание на строку анкеты и на её
    разбор из резюме. Разойдись эти два, проверка «разобранное легло в анкету»
    сравнивала бы двух разных людей.
    """
    return {
        "first_name": "Иван",
        "last_name": "Петров",
        "title": "Python-разработчик",
        "email": "ivan@example.com",
        **overrides,
    }


CV_REQUIRED_PROFILE = person_fields()
"""Минимум полей анкеты, без которого разбор резюме отдаёт пустоту.

Тот же человек, что и везде: разойдись они, проверка «разобранное легло в
анкету» сравнивала бы двух разных.
"""


def profile_row(**overrides) -> Profile:
    """Строка профиля кандидата. Обязательные поля заполнены."""
    return Profile(**person_fields(**overrides))


def profile_skill_row(profile_id: int, name: str, **overrides) -> ProfileSkill:
    """Строка навыка профиля. Имя задаётся явно: по нему навык и ищут."""
    return profile_skill(name, profile_id=profile_id, **overrides)


def experience_fields(**overrides) -> dict:
    """Умолчания места работы — одни и на строку в базе, и на разобранное из
    резюме. Дата начала обязательна на уровне базы, поэтому задана.
    """
    return {
        "company": "Контур",
        "company_url": None,
        "role": "Разработчик",
        "start_date": date(2020, 1, 1),
        "end_date": None,
        "achievements": [],
        "responsibilities": [],
        **overrides,
    }


def experience_row(profile_id: int, **overrides) -> ProfileExperience:
    """Строка места работы."""
    return ProfileExperience(profile_id=profile_id, **experience_fields(**overrides))


def blacklist_row(kind: str, value: str, **overrides) -> Blacklist:
    """Строка чёрного списка. Род и значение задаются явно: по ним и ищут."""
    fields = {"reason": None, "active": True}
    fields.update(overrides)
    return Blacklist(kind=kind, value=value, **fields)


def message_row(**overrides) -> Message:
    """Строка переписки. Текст обязателен на уровне базы."""
    fields = {
        "text": "здравствуйте",
        "is_incoming": True,
        "hr_id": None,
        "vacancy_id": None,
        "sent_at": EPOCH,
    }
    fields.update(overrides)
    return Message(**fields)


def unread_probe(hr_id: int) -> list[Message]:
    """Четыре письма одного человека, из которых непрочитанным считается ровно
    одно.

    Рядом с подходящим лежит по нарушителю каждого из трёх условий:
    прочитанное, наше и удалённое. Отпадёт любое условие — счётчик изменится,
    и это единственная причина, по которой набор именно такой. Собран здесь
    один раз: считают непрочитанное четверо — подвал, карточка, перечень и
    всплывающий список у подвала, — и разойдись их обстановки, ослабленное
    условие осталось бы под сторожем только у одного из четырёх.
    """
    return [
        message_row(hr_id=hr_id, text="подходит", is_incoming=True, read_at=None),
        message_row(hr_id=hr_id, text="прочитано", is_incoming=True, read_at=at(10)),
        message_row(hr_id=hr_id, text="наше", is_incoming=False, read_at=None),
        message_row(
            hr_id=hr_id, text="удалено", is_incoming=True, read_at=None,
            is_deleted=True,
        ),
    ]


def unread_probe_with_a_neighbour(hr_id: int, other_hr_id: int) -> list[Message]:
    """Тот же набор плюс непрочитанное соседа — четвёртый нарушитель.

    Счётчик у карточки и в перечне считает непрочитанное одного человека, а
    не всех сразу: отбор по хозяину — такое же условие, как «входящее» и
    «неудалённое», и снимается так же молча. Подвал в этот набор не входит
    нарочно — он как раз складывает по всем, и сосед был бы там не
    нарушителем, а слагаемым.
    """
    return [
        *unread_probe(hr_id),
        message_row(hr_id=other_hr_id, is_incoming=True, read_at=None),
    ]


def channel_marks() -> list[Blacklist]:
    """Три отметки, которыми проверяется правило «канал в чёрном списке»:
    включённая своего рода, снятая своего рода и включённая чужого.

    Обстановка одна на всех, кто это правило читает: карточка, перечень и
    опознание. Разойдись они — снятая отметка осталась бы проверенной на
    одном экране и забытой на другом.
    """
    return [
        blacklist_row("channel", "@listed"),
        blacklist_row("channel", "@off", active=False),
        blacklist_row("hr", "@hr_like"),
    ]


def marked_channels() -> list[TelegramChannel]:
    """Три канала под отметки `channel_marks()`: в списке, со снятой отметкой и
    чужого рода.

    Ники здесь — вторая половина самих отметок (`@listed`, `@off`,
    `@hr_like`), и порознь эти половины расходятся молча: переименуй ник в
    одной из них, и на трёх экранах проверка «отметки нет» останется зелёной
    по другой причине, чем задумана. Заголовки заданы затем, что перечень
    каналов раскладывает ответ по ним.
    """
    return [
        channel_row(username="listed", title="В списке"),
        channel_row(username="off", title="Отметка снята"),
        channel_row(username="hr_like", title="Чужой род"),
    ]


# Имена трёх компаний, на которых проверяется отметка чёрного списка: в
# списке, со снятой отметкой и чужого рода. Имя — единственное, чем компания
# связана с отметкой, поэтому обе половины обстановки берут его отсюда:
# записанные порознь, они разъехались бы молча, и проверка «отметки нет»
# осталась бы зелёной по другой причине, чем задумана.
_MARKED_COMPANIES = ("Контур", "Ромашка", "Берёзка")


def company_marks() -> list[Blacklist]:
    """Три отметки, которыми проверяется правило «компания в чёрном списке»:
    включённая своего рода, снятая своего рода и включённая чужого.

    То же, что `channel_marks()`, но по другому роду записи: правило читают
    карточка компании и перечень компаний, и собранное порознь оно
    разъезжалось бы молча — снятая отметка осталась бы проверенной на одном
    экране и забытой на другом.
    """
    listed, switched_off, other_kind = _MARKED_COMPANIES
    return [
        blacklist_row("company", listed),
        blacklist_row("company", switched_off, active=False),
        blacklist_row("hr", other_kind),
    ]


def marked_companies() -> list[Company]:
    """Три компании под отметки `company_marks()`: в списке, со снятой
    отметкой и чужого рода.
    """
    return [company_row(name=name) for name in _MARKED_COMPANIES]


def vacancy_event_row(vacancy_id: int, **overrides) -> VacancyEvent:
    """Событие обработки вакансии. Метка времени задаётся явно — по ней сортируют."""
    fields = {"kind": "parsed", "created_at": EPOCH}
    fields.update(overrides)
    return VacancyEvent(vacancy_id=vacancy_id, **fields)


def status_history_row(vacancy_id: int, **overrides) -> VacancyStatusHistory:
    """Запись о смене статуса. Метка времени задаётся явно — по ней сортируют."""
    fields = {
        "status": VacancyStatus.APPLIED,
        "previous_status": VacancyStatus.NEW,
        "source": StatusHistorySource.USER,
        "changed_at": EPOCH,
    }
    fields.update(overrides)
    return VacancyStatusHistory(vacancy_id=vacancy_id, **fields)


def tg_creds(**overrides) -> TgAccountConfig:
    """Учётные данные Telegram — свёртка, которую принимает запись настроек.

    Пароль и строка сеанса заданы пустыми: у самой свёртки умолчаний нет
    нарочно — пропущенное поле стирает записанный секрет, — а проверкам,
    которые об этих полях не говорят, называть их каждый раз незачем.
    """
    fields = {
        "api_id": 1,
        "api_hash": "шифр",
        "phone": "+79991234567",
        "password": "",
        "session_string": None,
    }
    fields.update(overrides)
    return TgAccountConfig(**fields)
