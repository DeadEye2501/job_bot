"""Резюме к письму: файл, а нет файла — ссылка на резюме из анкеты.

Отдельно от писем Telegram и почты: правило одно на оба способа, и порознь
оно разошлось бы — один отправлял бы со ссылкой, другой пропускал.
"""

from dataclasses import dataclass
from pathlib import Path

from backend.repository.profile import get_profile


@dataclass(frozen=True, slots=True)
class LetterResume:
    """Чем письмо несёт резюме: вложением или строкой ссылки — ровно одним."""

    file: Path | None
    link: str | None

    def under(self, body: str) -> str:
        """Текст письма со строкой ссылки в конце, если резюме идёт ссылкой.

        Строку дописывает код, а не модель: модель адреса не набирает, а
        проверка письма, отбивающая слово «резюме», идёт до этой строки.
        Строка — голый адрес: письмо пишется на языке вакансии, и подпись на
        любом одном языке была бы в нём чужой.
        """
        return f"{body}\n\n{self.link}" if self.link else body


async def resume_for_letter(pipeline) -> LetterResume | None:
    """Файл резюме, а нет файла — ссылка из анкеты; нет ни того ни другого — пусто."""
    resume = pipeline.cv_file()
    if resume is not None:
        return LetterResume(resume, None)
    async with pipeline.session_factory() as session:
        profile = await get_profile(session)
    if profile is None or not profile.resume_url:
        return None
    return LetterResume(None, profile.resume_url)
