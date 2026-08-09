"""Перечисления, которыми колонки ограничивают набор значений."""

import enum


class BotMode(enum.Enum):
    OFF = "Off"
    DM_ONLY = "DM Only"
    FULL = "Full"


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
