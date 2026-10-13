"""Подтвердить отправку у человека: одна точка для всех способов отклика.

В режиме «с подтверждением» перед отправкой введённого откликатель показывает
человеку пункты — что уйдёт — и ждёт его тем же ожиданием, что капча: правленые
пункты уходят вместо исходных, «Закончить» бросает вакансию.

Отличие от `human_gate`: там механика ожидания, здесь — о чём спрашивают: пункты,
ссылка на вакансию и чтение ответа окна.
"""

from typing import Literal, TypedDict

from backend.agent.jobs import Dropped
from backend.agent.kit import AgentKit
from backend.repository.vacancy_contacts import vacancy_link


# По этому типу MCP строит схему пункта для агента. Не пара скрининга: поле,
# которое анкете нечем заполнить, приходит пустым, и пустое значение законно.
class ConfirmItem(TypedDict):
    """Пункт окна подтверждения: подпись поля (у письма пусто), вид, значение,
    ошибка поля с сайта при повторном показе и селектор поля на странице (у
    письма Telegram и почты страницы нет — пусто)."""

    label: str
    kind: Literal["text", "choice", "check"]
    value: str
    error: str
    selector: str


def text_item(label: str, value: str) -> ConfirmItem:
    """Пункт письма или его темы: правится текстом, страницы у него нет."""
    return {"label": label, "kind": "text", "value": value, "error": "", "selector": ""}


def is_checked(item: ConfirmItem) -> bool:
    """Отметка галочки: окно пишет её словом, как и прочие значения."""
    return item["value"] == "true"


def confirming(kit: AgentKit) -> bool:
    """Ждать ли человека перед отправкой — решается здесь для всех способов."""
    return kit.pipeline.rs.auto_apply == "confirm"


async def confirmed(kit: AgentKit, vacancy_id: int, items: list[ConfirmItem]) -> list[ConfirmItem] | Dropped:
    """Пункты, какими их отправить: в режиме подтверждения — как их оставил
    человек, иначе — как есть."""
    if not confirming(kit):
        return items
    return await ask_person(kit, vacancy_id, items)


async def ask_person(kit: AgentKit, vacancy_id: int, items: list[ConfirmItem]) -> list[ConfirmItem] | Dropped:
    """Пункты, какими их оставил человек, или `Dropped`, если он закончил или
    обход остановили: в обоих случаях ничего не уходит. Срок обрывает прогон
    из самого ожидания."""
    async with kit.pipeline.session_factory() as session:
        link = await vacancy_link(session, vacancy_id)
    answer = await kit.gate.ask("confirm", "", {"url": link, "items": items})
    if answer is None or answer.get("drop"):
        return Dropped()
    return answer["items"]
