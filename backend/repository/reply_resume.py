"""Резюме к отклику: какое (`domain/resume_choice`), чем его несёт письмо и что
прикладывается к форме.

Одно на письма Telegram, почту, браузер и анкету агента: порознь правило
разошлось бы — один отправлял бы со ссылкой, другой пропускал. Файлы даёт
зовущий: что лежит на диске, знает конвейер, а не база.
"""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.resume_choice import ResumeSlot, reply_slot
from backend.repository.profile import get_profile


@dataclass(frozen=True, slots=True)
class ReplyResume:
    """Резюме к отклику: его файл и ссылка, чьё оно и файл для формы.

    `form_file` расходится с `file` в одном случае: у основного файла нет, а
    английский есть — к форме он идёт, английское резюме к русской вакансии
    уместно. Обратного нет: русское к английской вакансии не прикладывают.
    Письмо так не делает: ему хватает ссылки.
    """

    file: Path | None
    link: str | None
    slot: ResumeSlot
    form_file: Path | None

    def under(self, body: str) -> str:
        """Текст письма со строкой ссылки в конце, если резюме идёт ссылкой —
        без файла.

        Строку дописывает код, а не модель: модель адреса не набирает, а
        проверка письма, отбивающая слово «резюме», идёт до этой строки.
        Строка — голый адрес: письмо пишется на языке вакансии, и подпись на
        любом одном языке была бы в нём чужой.
        """
        return f"{body}\n\n{self.link}" if self.file is None and self.link else body


async def reply_resume(
    session: AsyncSession, main_file: Path | None, english_file: Path | None, language: str
) -> ReplyResume | None:
    """Резюме к отклику на `language`; нет ни основного, ни английского — пусто.
    Файлы — лежащие на диске, пусто — файла нет."""
    profile = await get_profile(session)
    given: dict[ResumeSlot, tuple[Path | None, str | None]] = {
        "main": (main_file, profile.resume_url if profile else None),
        "english": (english_file, profile.resume_url_en if profile else None),
    }
    slot = reply_slot(language, any(given["main"]), any(given["english"]))
    if slot is None:
        return None
    file, link = given[slot]
    form_file = file or (english_file if slot == "main" else None)
    return ReplyResume(file, link, slot, form_file)
