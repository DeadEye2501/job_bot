"""Свёртки значений, ходящих между слоями.

Дом нейтральный нарочно. Собирает эти значения одна сторона — разбор моделью,
чтение Telegram, запрос репозитория, — а читает другая, и держи их у любой из
двух, встречный ввоз завёл бы круг: репозиторий знал бы про слой модели, слой
модели про мост.

Своей работы здесь почти нет, и то, что есть, — про эти же значения:
`ParsedVacancy.stack` складывает две половины стека для тех, кому деление не
нужно, а `DIRECT_PARSED_FIELDS` перечисляет поля, переносимые из разбора в
строку один в один, — перечень тоже про эти значения и живёт рядом с ними, а не
у переносящего.

Приведение отдельного значения сюда не входит и живёт в `backend/incoming.py`:
свёртки читает весь проект, а приведение — только те, кто принимает чужое.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, get_args

from backend.models import (
    HR,
    Company,
    TelegramChannel,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
    VacancyStatusHistory,
)


DIRECT_PARSED_FIELDS = (
    "title",
    "description",
    "company_name",
    "hr_contact",
    "grade",
    "salary",
    "remote",
    "location",
)
"""Прямые поля разбора: у модели они лежат один в один, без пересчёта, и имя
у вакансии то же самое.

Перечень один на четверых — стереть прошлое, записать новое, назвать
заполненное и собрать разобранное обратно из строки для ручного отклика, —
потому что зеркальны эти четверо только по уговору: забытое в одном из них
поле оставит на экране прошлый разбор, и молча. Дом нейтральный: разбор
(`flows/parse`) и отправка отклика (`flows/apply`) уже связаны ввозом в одну
сторону, и встречный завёл бы круг.

Производные — стек с оценкой, тройка зарплаты и заметки — сюда не входят: у
каждого своё правило, и оно живёт в теле.
"""


FitVerdict = Literal["fit", "reject", "trash"]
# Те же три значения, но набором — для разбора ответа модели. Берутся из
# самого объявления, чтобы список и тип не разъехались.
FIT_VERDICTS: tuple[str, ...] = get_args(FitVerdict)


@dataclass(frozen=True)
class ChannelPost:
    """Пост канала в том виде, в каком его принимает конвейер: откуда взят
    и что в нём написано.

    Четыре значения ходят вместе от чтения канала до записи вакансии, и
    порознь ни одно из них не значит ничего: `text` — уже извлечённый из
    `msg`, а ник нужен и для ссылки, и для следа в журнале.
    """
    channel_id: int | None
    channel_username: str
    msg: Any
    text: str


@dataclass(frozen=True)
class OutgoingMessage:
    """Наше письмо HR в том виде, в каком оно уже ушло в Telegram.

    Одно и то же письмо приходит к нам двумя дорогами — из окна, когда мы
    его отправили, и эхом из Telegram, когда его увидел другой клиент, — и
    оба раза записывается одинаково. Значения ходят вместе: без номера
    сообщения не распознать повтор, без времени письмо не встанет в
    переписке на своё место.

    Вакансия пустует у всех, кроме отклика: эхо и догон знают только
    переписку, а к вакансии письмо привязывает лишь тот, кто по ней и
    отвечал.
    """
    hr_id: int
    text: str
    tg_message_id: int
    sent_at: Any
    vacancy_id: int | None = None
    media_kind: str | None = None
    media_path: str | None = None
    media_name: str | None = None


@dataclass(frozen=True)
class IncomingMessage:
    """Письмо HR в том виде, в каком оно ложится в переписку.

    Зеркало `OutgoingMessage`: восемь значений об одном письме, те же и в том
    же составе, включая вакансию, к которой письмо отнесли. Ходят они вместе — без номера не
    распознать повтор, без времени письмо не встанет в переписке на своё
    место, а без вакансии переписка не свяжется с откликом.

    Вакансия здесь может пустовать, и это не забывчивость: письмо от HR,
    которому мы ещё не писали, относить не к чему.
    """
    hr_id: int
    vacancy_id: int | None
    text: str
    tg_message_id: int
    received_at: Any
    media_kind: str | None = None
    media_path: str | None = None
    media_name: str | None = None


@dataclass(frozen=True)
class PendingReply:
    """Письмо HR, ждущее отложенного разбора.

    Номера у письма два, и нужны оба. По номеру строки записывается вердикт:
    на него ссылается история статуса вакансии. По номеру Telegram письмо
    находят правка и удаление — оповещения о них другого номера не знают.

    Сведи их в один, и разойдутся они молча: правка уйдёт в пустоту, и модель
    разберёт текст, которого HR уже не писал, а удалённое письмо из копилки
    не выпадет и продолжит двигать статус вакансии.
    """
    vacancy_id: int
    message_id: int
    tg_message_id: int
    text: str


# Разобранное резюме — пять связанных значений об одном человеке. Живут здесь
# по тому же договору, что и разобранная вакансия: разбор их собирает, а
# читает анкета, то есть держать их у разбора значило бы вести ввоз из
# репозитория в слой модели.
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


@dataclass(frozen=True)
class Classification:
    status: VacancyStatus
    explanation: str | None


@dataclass(frozen=True)
class ParsedVacancy:
    title: str
    description: str | None
    company_name: str | None
    company_website: str | None
    hr_contact: str | None
    # Любой нон-Telegram способ откликнуться, который LLM нашёл в посте
    # (email, ссылка на форму отклика, careers-страница, ссылка на job-
    # площадку, явная инструкция «писать в комментариях»). Берётся
    # дословно из текста поста. Сохраняется в ``Vacancy.notes`` строкой
    # «Контакты: <other_contact>» — у юзера должен быть способ
    # откликнуться даже когда TG-контакта в посте нет. None если в
    # посте никакого контакта кроме (или включая) TG-аккаунта.
    other_contact: str | None
    # Stack split into "обязательные" (required) and "будет плюсом" (preferred)
    # at parse time by the LLM. Both lists are already canonicalized,
    # version-stripped, capitalized and unique across BOTH lists (the LLM is
    # explicitly instructed not to put the same skill into both groups). The
    # split is consumed by ``score_parsed`` for weighting and by
    # ``validate_vacancy_fit`` (sees both lists separately); everywhere else
    # (UI chips, DB ``Vacancy.stack`` column) reads ``stack`` — see the
    # property below — which simply joins both lists in declaration order.
    stack_required: list[str]
    stack_preferred: list[str]
    grade: str | None
    salary: str | None
    remote: str | None
    location: str | None

    @property
    def stack(self) -> list[str]:
        """Объединённый стек (required + preferred) — потребители этого
        view не нуждаются в делении: запись в БД-колонку ``Vacancy.stack``,
        ``is_empty_vacancy``-чек, отображение в UI. Возвращаем новый list,
        не view — чтобы случайная мутация у потребителя не утекла в
        required/preferred.
        """
        return list(self.stack_required) + list(self.stack_preferred)


@dataclass(frozen=True)
class FitValidation:
    verdict: FitVerdict
    reason: str | None


@dataclass(frozen=True)
class VacancyDetail:
    vacancy: Vacancy
    history: list[VacancyStatusHistory]
    events: list[VacancyEvent]


@dataclass(frozen=True)
class HrWithCount:
    hr: HR
    vacancy_count: int
    last_company_name: str | None
    unread_count: int = 0
    is_blacklisted: bool = False


@dataclass(frozen=True)
class HrDetail:
    """Full payload for the Contacts / HR detail pane (05).

    ``last_company_id`` complements ``last_company_name`` so the UI can
    deep-link into the Companies tab on click. ``unread_count`` powers the
    «N непрочитанных» chip in the head. ``blacklist_value`` is non-NULL
    when an active row exists in the blacklist table for this HR — UI
    paints a red chip + flips the menu item to «Убрать из blacklist».
    """
    hr: HR
    vacancy_count: int
    last_company_id: int | None
    last_company_name: str | None
    unread_count: int
    blacklist_value: str | None = None


@dataclass(frozen=True)
class CompanyDetail:
    """Full payload for the Contacts/Companies detail pane (06).

    ``hr_count`` = distinct HRs with at least one vacancy at this company,
    powering the «N HR» chip in the head. ``blacklist_value`` is non-NULL
    when an active row exists in the blacklist table for this company —
    UI paints the red chip + flips the menu item to «Убрать из blacklist».
    """
    company: Company
    vacancy_count: int
    hr_count: int
    blacklist_value: str | None = None


@dataclass(frozen=True)
class CompanyWithCount:
    company: Company
    vacancy_count: int
    is_blacklisted: bool = False


@dataclass(frozen=True)
class ChannelWithCount:
    channel: TelegramChannel
    vacancy_count: int
    is_blacklisted: bool = False


@dataclass(frozen=True)
class ChannelStats:
    """Computed stats for the Contacts/Channels detail pane.

    All counts are over the full lifetime of the channel; only
    ``vacancies_per_day`` is windowed (last 30 days) — это про «пропускная
    способность сейчас», а не средняя за всю историю канала.

    ``status_counts`` keys are ``VacancyStatus.value`` strings (e.g.
    ``"New"``, ``"Applied"``) so the frontend can drive the breakdown bar
    and legend without a server-side ordering choice.
    """
    status_counts: dict[str, int]
    total: int
    vacancies_per_day: float
    # KPI ratios as integer percent, 0-100. None when the denominator is 0
    # (UI shows «—» вместо «0%», иначе пустой канал выглядит как
    # провальная воронка).
    fit_percent: int | None
    apply_percent: int | None
    response_percent: int | None


@dataclass(frozen=True)
class ChannelDetail:
    channel: TelegramChannel
    stats: ChannelStats
    blacklist_value: str | None = None


@dataclass(frozen=True)
class VacancyFilter:
    """Отбор списка вакансий: что показать, в каком порядке и сколько.

    Шестнадцать значений об одном предмете — что именно человек выбрал в
    окне, — и порознь они не ходят: экран шлёт их одной пачкой, а список
    складывает все непустые через И.

    - ``sort`` — ключ порядка; незнакомый молча становится «сначала
      свежие».
    - ``search`` — подстрока без учёта регистра по названию, описанию,
      имени компании (и своему, и связанной), заметкам, зарплате, грейду,
      имени и нику HR, плюс по сырому JSON стека.
    - ``statuses`` — коды статусов через дефис (`in-progress`); собирает их
      `models.status_code`. Незнакомый код отбрасывается, но не молча — о нём
      пишется в журнал: для человека это «фильтр нажат и не действует», и
      причину ему больше взять неоткуда.
    - ``channels`` — ники каналов без учёта регистра. Вакансия без канала
      не совпадает никогда.
    - ``companies`` — имена компаний без учёта регистра; совпадает и со
      связанной строкой, и с сырым именем, чтобы непривязанные вакансии
      тоже находились.
    - ``score_min`` / ``score_max`` — целые границы; вакансия без баллов
      не совпадает никогда.
    - ``salary_min`` / ``salary_max`` — окно, которое обязано пересечься с
      вилкой вакансии; обе границы включительны. Строка, где чисел не
      нашлось, не совпадает ни с каким окном, а вот названная одна сторона
      («от 300 000», «до 120 000») окну не противоречит и проходит его:
      пустая сторона значит «неизвестно», а не «столько же». Валюта не
      спрашивается — числа сравниваются как записаны.
    - ``grade`` / ``remote`` — подстрока по своей колонке.
    - ``hr_contact`` — `"with"` или `"without"` по наличию HR; всё прочее
      (включая `None` и `"all"`) ничего не отбирает.
    - ``date_from`` / ``date_to`` — границы по метке активности, той же,
      по которой идёт порядок.
    - ``limit`` / ``offset`` — страница; без предела смещение не читается.
    """

    sort: str = "newest"
    search: str | None = None
    statuses: list[str] | None = None
    channels: list[str] | None = None
    companies: list[str] | None = None
    score_min: int | None = None
    score_max: int | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    grade: str | None = None
    remote: str | None = None
    hr_contact: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int | None = None
    offset: int = 0


