"""Подтвердить отправку у человека: одна точка для всех способов отклика.

В режиме «с подтверждением» перед отправкой введённого откликатель показывает
человеку пункты — что уйдёт — и ждёт его тем же ожиданием, что капча: правленые
пункты уходят вместо исходных, «Закончить» бросает вакансию. В прочих режимах
пункты уходят как есть.

Пункт — `{label, kind, value, error}`: подпись поля (письмо — без подписи), вид
(`text`, `choice`, `check`), значение и ошибка поля с сайта при повторном показе.
"""

from backend.agent.kit import AgentKit
from backend.applying.result import Dropped
from backend.repository.vacancy_contacts import vacancy_link


def text_item(label: str, value: str) -> dict:
    """Пункт, который правят текстом."""
    return {"label": label, "kind": "text", "value": value, "error": ""}


async def confirmed(kit: AgentKit, vacancy_id: int, items: list[dict]) -> list[dict] | Dropped:
    """Пункты, какими их оставил человек, или `Dropped`, если он закончил или
    обход остановили: в обоих случаях ничего не уходит. Срок обрывает прогон
    из самого ожидания."""
    if kit.pipeline.rs.auto_apply != "confirm":
        return items
    async with kit.pipeline.session_factory() as session:
        link = await vacancy_link(session, vacancy_id)
    answer = await kit.gate.ask("confirm", "", {"url": link, "items": items})
    if answer is None or answer.get("drop"):
        return Dropped()
    return answer["items"]
