"""Подсказки «кого предложить в чёрный список» для окна заведения."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company, HR

from backend.repository.blacklist_marks import preferred_blacklist_value
from backend.repository.channels import (
    channel_blacklist_candidates,
    list_named_channels,
)
from backend.repository.companies_card import company_blacklist_candidates
from backend.repository.hr_card import hr_blacklist_candidates
from backend.repository.hr_identify import HAS_TELEGRAM_IDENTITY


def _by_label(rows: list[dict]) -> list[dict]:
    """Подсказки по подписи, без учёта регистра.

    Порядок общий у трёх вкладок одного окна: человек ходит между ними, а
    сравнение базы идёт по кодам символов — заглавные встали бы впереди
    строчных на одной вкладке из трёх.
    """
    rows.sort(key=lambda row: (row["label"] or "").casefold())
    return rows


def _named_candidates(named: list[tuple[str | None, str | None]]) -> list[dict]:
    """Строки списка «добавить в чёрный список» у предмета с названием.

    Принимает пары «отсеиваемое значение, название». Годится тем, у кого
    название отдельно от значения: у собеседника это имя против ника, у
    канала — заголовок против ника. Компания такой формы не имеет —
    уточнением там служит сайт, а порядок задаёт сам запрос.
    """
    out: list[dict] = []
    for value, title in named:
        if value is None:
            continue
        out.append({"value": value, "label": title or value, "sub": value if title else None})
    return _by_label(out)


async def _company_candidates(session: AsyncSession) -> list[dict]:
    """Строки подсказки по компаниям: значение и подпись — имя, ниже сайт.

    Своей формой, а не общей `_named_candidates`: у компании названия отдельно
    от значения нет — уточнением служит сайт. Порядок при этом общий, `_by_label`.
    """
    out: list[dict] = []
    for co in (await session.scalars(select(Company))).all():
        value = preferred_blacklist_value(company_blacklist_candidates(co))
        if value is None:
            continue
        out.append({"value": value, "label": co.name, "sub": co.website or None})
    return _by_label(out)


async def list_blacklist_candidates(
    session: AsyncSession, kind: str
) -> list[dict]:
    """Список options для combobox'а add-modal'а blacklist'а.

    Список — подсказка, а не закрытый набор, и это решение человека от
    13.08.2026: рядом с ним человек набирает значение руками, чтобы завести в
    список ник, которого в базе ещё нет. Появится такой HR или канал — попадёт
    под уже заведённую строку сразу, а не после того, как о нём вспомнят.

    Плата за это — написание не проверяется, и от рода записи зависит, чем
    оно обернётся. Отметку на экранах HR, компаний и каналов ставит точное
    сравнение со строгими написаниями (`@ник`, `user_id:номер`, имя компании):
    набранный без собачки `ник` там не совпадёт никогда, и HR продолжит писать.
    Ослабить это сравнение нельзя — им же три экрана показывают отметку, и
    разойдись оно, разойдутся и они. А вот в тексте объявления значение ищется
    независимо от рода (`load_active_blacklist_patterns` берёт все подряд), и
    там тот же `ник` сработает по границам слова — не там, где имелось в виду.

    Каждая строка — `{value, label, sub?}`, порядок по подписи. Незнакомый
    род и ключевое слово подсказок не имеют: последнее набирают свободно.
    """
    if kind == "hr":
        rows = (
            await session.scalars(select(HR).where(HAS_TELEGRAM_IDENTITY))
        ).all()
        return _named_candidates(
            [
                (preferred_blacklist_value(hr_blacklist_candidates(hr)), hr.name)
                for hr in rows
            ]
        )
    if kind == "company":
        return await _company_candidates(session)
    if kind == "channel":
        return _named_candidates(
            [
                (
                    preferred_blacklist_value(channel_blacklist_candidates(ch)),
                    ch.title,
                )
                for ch in await list_named_channels(session)
            ]
        )
    return []
