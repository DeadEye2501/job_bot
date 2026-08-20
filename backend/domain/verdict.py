"""Приговор разобранному объявлению до того, как оно войдёт в граф статусов."""

from backend.models import VacancyStatus
from backend.payloads import ParsedVacancy

# Метки приговора в `skip_reason`: их пишет разбор, по ним же считает мусор
# экран каналов. Объявлены здесь, рядом с приговором, — иначе одна сторона
# сменила бы написание, а вторая молча перестала бы находить свои строки.
EMPTY_SKIP_PREFIX = "empty: "
EMPTY_SKIP_REASON = f"{EMPTY_SKIP_PREFIX}no meaningful fields"
TRASH_SKIP_PREFIX = "trash: "

JUNK_SKIP_PREFIXES = (TRASH_SKIP_PREFIX, EMPTY_SKIP_PREFIX)
"""Обе метки, которыми помечен пост, не бывший вакансией.

Разбор их различает — отвергнутое вердиктом и пустое, — а счёт каналов нет:
для него это одно, «канал прислал не вакансию». При обычном разборе такая
строка удаляется и ложится в отметки мусора одной кучей; при повторном
остаётся, и по одной метке из двух половина её терялась.
"""
# Метка отказа самой модели — тем же правилом, что и мусор: причину пишет
# разбор, читает её экран вакансии.
LLM_SKIP_PREFIX = "llm: "

TRUNCATED_SKIP_REASON = f"{LLM_SKIP_PREFIX}ответ модели не поместился"
"""Метка вакансии, которую модель не смогла уложить в ответ даже с запасом.

Обрыв ответа приговором не является, и строка ждёт следующего захода — но
ждать вечно она не может: подбор недоразобранного берёт её при каждом запуске
и платит полным разбором. Переспросить с поднятым потолком модель к этому мигу
уже пробовала (`llm/answers.wants_more_room`), значит дальше это дело
человека: строка ложится в окно с этой причиной и разбирается заново по
кнопке.

Меткой мусора не считается нарочно: пост, скорее всего, настоящая вакансия, и
удалять его нельзя — разбор не удался у нас, а не у него.
"""


def is_empty_vacancy(parsed: ParsedVacancy | None) -> bool:
    """True если вакансия — очевидная пустышка/мусор и должна уходить в trash
    без обращения к LLM-валидатору.

    Критерии:
    - parsed is None — LLM не извлёк даже title.
    - title есть, но из 5 ключевых полей (description, stack, hr_contact,
      company_name, salary) заполнено МЕНЬШЕ ДВУХ. Раньше требовалось
      чтобы ВСЕ четыре отсутствовали (description+stack+hr_contact+
      company_name) — это съедало валидные короткие посты типа
      «Junior дизайнер | удалёнка | контакт @anna_hr» (есть title +
      hr_contact, остальное пусто → trash). Теперь нужны хотя бы ДВА
      сигнала из пяти.
    """
    if parsed is None:
        return True
    signals = (
        bool(parsed.description),
        bool(parsed.stack),
        bool(parsed.hr_contact),
        bool(parsed.company_name),
        bool(parsed.salary),
    )
    return sum(signals) < 2


def decide_vacancy_status(
    parsed: ParsedVacancy,
    score: int,
    blacklist_match: str | None,
    *,
    threshold: int,
) -> tuple[VacancyStatus, str | None]:
    """Приговор разобранному объявлению: статус и причина отказа.

    Разбора без объявления сюда не приходит: пустой разбор — это пустышка, и
    её приговор выносит `is_empty_vacancy` куда раньше.
    """
    if blacklist_match:
        return VacancyStatus.NOT_FIT, f"blacklist: {blacklist_match}"
    if score < threshold:
        return VacancyStatus.NOT_FIT, f"score {score} < {threshold}"
    return VacancyStatus.NEW, None
