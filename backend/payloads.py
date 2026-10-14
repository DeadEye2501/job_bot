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
from typing import Any, Literal, NamedTuple

from backend.domain.stack import joined_stack
from backend.models import (
    HR,
    Company,
    Gender,
    SalaryPeriod,
    TelegramChannel,
    Vacancy,
    VacancyContact,
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
поле оставит на экране прошлый разбор, и молча. Дом нейтральный: читают его
и разбор (`flows/parse`), и письмо отклика (`applying/telegram_letter`), а
друг друга они не ввозят.

Производные — стек с оценкой и тройка зарплаты — сюда не входят: у каждого
своё правило, и оно живёт в теле. Найденный контакт ложится не колонкой, а
строкой `vacancy_contact`.
"""


# Чем вердикт о вакансии бывает вообще. Что из этого вправе ответить зов о
# пригодности — набор уже (`llm/fit.ASKED_VERDICTS`): «мусор» выносит только
# зов о жанре, и по нему вакансию удаляют насовсем.
FitVerdict = Literal["fit", "reject", "trash"]


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
REQUIRED_PROFILE_FIELDS: tuple[str, ...] = (
    "first_name",
    "last_name",
    "title",
    "email",
)
"""Поля анкеты, без которых её не сохранить.

Объявление одно на всех, потому что спрашивают о них трое: колонки без них
не заполнить (`models/profile`), окно отказывает в сохранении, а разбор
резюме без них отдаёт пустоту вместо анкеты. Разъедься перечни — разбор
вернул бы анкету, которую окно откажется принять.
"""


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
    expected_salary: int | None
    expected_salary_currency: str | None
    expected_salary_period: SalaryPeriod | None
    first_name_latin: str | None
    last_name_latin: str | None
    gender: Gender | None
    patronymic: str | None
    patronymic_latin: str | None
    birth_date: date | None
    citizenship: str | None
    about_me: str | None
    resume_url: str | None


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
class ParsedCvProject:
    name: str
    url: str | None
    about: list[str]
    stack: list[str]


@dataclass(frozen=True)
class ParsedCv:
    profile: ParsedCvProfile
    languages: list[ParsedCvLanguage]
    skills: list[ParsedCvSkill]
    experience: list[ParsedCvExperience]
    projects: list[ParsedCvProject]
    # Язык основного текста резюме, как его назвала модель: родным он
    # становится, если резюме родного не называет.
    text_language: str | None


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
    # Все не-Telegram способы откликнуться, которые модель нашла в посте:
    # почта, форма, страница вакансий, ссылка на площадку — каждый своим
    # элементом и дословно. Каждый ложится своим контактом вакансии
    # (`vacancy_contact`, добавлен разбором). Пусто — кроме Telegram-аккаунта
    # в посте контакта нет.
    other_contacts: list[str]
    # Stack split into "обязательные" (required) and "будет плюсом" (preferred)
    # at parse time by the LLM. Both lists are already version-stripped,
    # capitalized and unique across BOTH lists (the LLM is explicitly
    # instructed not to put the same skill into both groups). The split is
    # consumed by ``score_stack`` for weighting and by ``validate_role_fit``
    # (sees both lists separately); everywhere else (UI chips, DB
    # ``Vacancy.stack`` column) reads ``stack`` — see the property below.
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
        ``is_empty_vacancy``-чек, отображение в UI.

        Складывает половины `domain/stack.joined_stack` — тот же, кем их
        складывает заведение руками: правило порядка одно на оба пути, а
        новый список вместо view он отдаёт затем, чтобы случайная мутация у
        потребителя не утекла в required/preferred.
        """
        return joined_stack(self.stack_required, self.stack_preferred)


@dataclass(frozen=True)
class PostGenre:
    """Жанр поста: зовёт ли автор кого-то на работу или предлагает себя.

    Отдельно от `FitValidation` потому, что отвечает на другой вопрос и
    спрашивается другим зовом, без анкеты кандидата. Слитые в один вопрос,
    они спорят: на посте, похожем на анкету, «подходит ли» перебивает
    «вакансия ли это».

    Обоснование обязательно и здесь: приговор без слов не проверить, а по
    этому приговору строку удаляют.
    """

    is_vacancy: bool
    reason: str


@dataclass(frozen=True)
class FitValidation:
    verdict: FitVerdict
    reason: str | None


@dataclass(frozen=True)
class VacancyDetail:
    vacancy: Vacancy
    history: list[VacancyStatusHistory]
    events: list[VacancyEvent]
    contacts: list[VacancyContact]
    has_screening: bool


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

    Счёта вакансий здесь нет: карточка его не показывала никогда, а считался
    он запросом на каждое её открытие. Число, которое человек видит, приезжает
    строкой перечня.
    """
    hr: HR
    last_company_id: int | None
    last_company_name: str | None
    unread_count: int
    blacklist_value: str | None = None


@dataclass(frozen=True)
class CompanyDetail:
    """Full payload for the Contacts/Companies detail pane (06).

    ``blacklist_value`` is non-NULL when an active row exists in the
    blacklist table for this company — UI paints the red chip + flips the
    menu item to «Убрать из blacklist».

    Счёта вакансий и счёта людей здесь нет: карточка их не показывала никогда,
    а считались они двумя запросами на каждое её открытие. Числа, которые
    человек видит, приезжают строкой перечня.
    """
    company: Company
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
class SourceStats:
    """Числа карточки источника вакансий — канала или агрегатора.

    Все счёты — за всю жизнь источника; только ``vacancies_per_day`` берётся
    окном в 30 дней — это про «пропускная способность сейчас», а не средняя
    за всю историю.

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
    stats: SourceStats
    blacklist_value: str | None = None


@dataclass(frozen=True)
class SeenResume:
    """Резюме, увиденное сканированием сайта. Места своего не несёт: место —
    порядок в списке, который сканирование отдаёт в порядке сайта."""

    title: str
    url: str


class FieldEntry(NamedTuple):
    """Поле в описи страницы: селектор, по которому его находит Playwright,
    подпись, вид (`text`, `textarea`, `select`, `check`, `radio`),
    обязательность и варианты — у списка и группы кружков. Снимает опись
    браузер (`agent/page_fields`), читает и проверяющий раскладки (`llm`)."""

    selector: str
    label: str
    kind: str
    required: bool
    options: list[str]


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


