"""Вакансия текстом для агента."""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.llm.external import external_block
from backend.models import Aggregator, TelegramChannel, Vacancy
from backend.repository.vacancy_contacts import list_contacts


async def describe_vacancy(session: AsyncSession, vacancy_id: int) -> str | None:
    """Вакансия текстом для агента. Пусто — вакансии нет.

    Одна сборка на инструмент `vacancy` и на задание откликателя: две подписи
    одного и того же разошлись бы, и агент увидел бы два описания своей
    вакансии. Текст страницы чужой — он идёт в рамке данных.
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return None
    contacts = [c.value for c in await list_contacts(session, vacancy_id)]
    return "\n".join([
        f"Вакансия: {vacancy.title or '—'}",
        f"Компания: {vacancy.company_name or '—'}",
        f"Источник: {await _source(session, vacancy)}",
        f"Адрес страницы вакансии: {vacancy.source_url or '—'}",
        f"Контакты вакансии: {', '.join(contacts) or '—'}",
        "",
        external_block(vacancy.raw_text or "", "текст вакансии со страницы"),
    ])


async def _source(session: AsyncSession, vacancy: Vacancy) -> str:
    if vacancy.source_aggregator_id is not None:
        site = await session.get(Aggregator, vacancy.source_aggregator_id)
        return site.name if site else "—"
    if vacancy.source_channel_id is not None:
        channel = await session.get(TelegramChannel, vacancy.source_channel_id)
        return f"@{channel.username}" if channel else "—"
    return "заведена человеком"
