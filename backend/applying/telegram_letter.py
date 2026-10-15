"""Письмо HR в Telegram: первое с резюме или вдогон без него."""

import logging
from dataclasses import dataclass

from backend.agent.kit import AgentKit
from backend.applying.resume_link import resume_for_letter
from backend.llm.cover_letter import LetterPost, generate_cover_letter
from backend.models import Vacancy
from backend.payloads import DIRECT_PARSED_FIELDS, ParsedVacancy

logger = logging.getLogger(__name__)

# Окно «недавно отправляли письмо этому HR» (см.
# count_recent_outgoing_with_vacancy_for_hr). Старше — шлём письмо с резюме,
# как первый раз.
RECENT_SEND_WINDOW_DAYS = 14


@dataclass(frozen=True, slots=True)
class Letter:
    """Письмо к отправке: текст и вложение к нему.

    У письма вдогон вложения нет никогда; у первого — файл резюме, а нет
    файла — ссылка на резюме в тексте и вложения нет.
    """

    text: str
    attachment: object | None


def format_channel_ref(channel_username: str | None) -> str | None:
    """Ник канала для письма с `@`; пусто — строки «Канал: …» не будет вовсе."""
    if not channel_username:
        return None
    s = channel_username.strip()
    if not s:
        return None
    return s if s.startswith("@") else f"@{s}"


async def compose_letter(kit: AgentKit, parsed: ParsedVacancy, post: LetterPost, vacancy_id: int):
    """Письмо модели; первое за окно — с резюме файлом или ссылкой, вдогон — без:
    резюме у HR уже есть. При беде — пара «пусто и код отказа».

    Письмо вдогон пишет та же модель, а не готовая строка: отклик целиком идёт
    на языке вакансии. Название и канал вплетает в текст сама модель: готовая
    приставка поверх живого письма читается штампом. Анкета — та же, что видит
    агент: на просьбу поста письмо отвечает из анкеты, и урезанная анкета
    отвечала бы «обсудим» на то, что в ней есть.
    """
    profile = await kit.read(kit.profile_text)
    if not profile:
        logger.warning("vacancy %d: анкета пуста, письмо не пишется", vacancy_id)
        return None, "profile_empty"
    pipeline = kit.pipeline
    body, trouble = await generate_cover_letter(
        profile, parsed, pipeline.lm_client, pipeline.lm_chat_model, post=post,
    )
    if trouble is not None:
        logger.warning("vacancy %d: письмо не сочинилось — модель не ответила (%s)",
                       vacancy_id, trouble)
        return None, "cover_letter_unasked"
    if body is None:
        logger.warning("vacancy %d: cover letter generation failed, skipping send", vacancy_id)
        return None, "cover_letter_failed"
    if post.earlier:
        return Letter(body, None), None
    resume = await resume_for_letter(pipeline)
    if resume is None:
        logger.warning("vacancy %d: CV file missing (%s), skipping send",
                       vacancy_id, pipeline.cv_path())
        return None, "cv_missing"
    return Letter(resume.under(body), resume.file), None


def parsed_from_row(v: Vacancy) -> ParsedVacancy:
    """Собрать разобранную вакансию обратно из строки базы.

    Прямые поля берутся перечнем `DIRECT_PARSED_FIELDS` — тем же, каким разбор
    их и записывал: со своим списком новое поле до письма не доехало бы молча.
    Пустое название становится пустой строкой, сайт компании и второй контакт
    в строке не хранятся, а стек хранится одним списком — в обязательный он и
    уходит: занизить требование хуже, чем завысить.
    """
    direct = {name: getattr(v, name) for name in DIRECT_PARSED_FIELDS}
    return ParsedVacancy(
        **{**direct, "title": v.title or ""},
        company_website=None,
        other_contacts=[],
        stack_required=list(v.stack or []),
        stack_preferred=[],
    )
