"""Перечисления, которыми колонки ограничивают набор значений."""

import enum


class BotMode(enum.Enum):
    OFF = "Off"
    DM_ONLY = "DM Only"
    FULL = "Full"


class Currency(enum.Enum):
    """Валюта зарплаты, как она названа в объявлении.

    Приведения к одной валюте нет: курс в объявлении не указан, а отбор в
    списке идёт по написанному числу. Не названная в строке валюта остаётся
    неизвестной, и колонка хранит пустоту."""

    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class VacancyStatus(enum.Enum):
    NEW = "New"
    APPLIED = "Applied"
    ANSWERED = "Answered"
    TEST = "Test"
    INVITATION = "Invitation"
    IN_PROGRESS = "In Progress"
    DECLINE = "Decline"
    GHOSTING = "Ghosting"
    SCAM = "Scam"
    NOT_FIT = "Not Fit"
    OFFER = "Offer"


def status_code(status: VacancyStatus) -> str:
    """Код положения дел, которым его называет окно.

    Правило: значение строчными, пробелы дефисами — `In Progress` становится
    `in-progress`. Разметка выводит код почти так же, и не в одном месте:
    `statusToClass` и второе, инлайновое, в строке показателей; отличие у них
    одно — они схлопывают подряд идущие пробелы, а здесь заменяется каждый.
    На нынешних одиннадцати значениях это одно и то же, и разойдётся только
    на значении с двойным пробелом внутри.
    Держать рядом с ними ещё и выписанную руками таблицу значило бы завести
    четвёртое написание — новое положение дел появлялось бы в перечислении, а
    отбор по нему молча не работал.
    """
    return status.value.lower().replace(" ", "-")


class StatusHistorySource(enum.Enum):
    """Кто сгенерировал запись в vacancy_status_history.

    SYSTEM — авто-классификация HR-реплая, авто-/ручная отправка отклика
    ботом, любые системные источники. Текст в ``explanation`` сгенерирован
    кодом или LLM, юзер его не писал.
    USER — пользователь руками сменил статус через UI, ``explanation``
    введён юзером и должен быть редактируемым."""

    SYSTEM = "system"
    USER = "user"


class LlmConfigKind(enum.Enum):
    CHAT = "chat"
    EMBED = "embed"
