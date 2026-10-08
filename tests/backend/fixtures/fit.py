"""Как тесты спрашивают зовы о пригодности — о роли, о языках.

Вопрос у зовов один и тот же, различаются они только наставлением, поэтому и
обёртка одна: какой зов спросить, приходит доводом.
"""

from backend.llm.candidate import CandidateProfile
from tests.factories import parsed_vacancy


async def asked(check, client, *, raw_text="обычный текст вакансии", profile=None, parsed=None):
    """Спросить зов о пригодности и отдать ответ целиком: вердикт и причину."""
    return await check(
        parsed or parsed_vacancy(),
        raw_text,
        client,
        "qwen",
        profile=profile or CandidateProfile(),
    )


async def verdict(check, client, *, raw_text="обычный текст вакансии", profile=None, parsed=None):
    """Спросить зов о пригодности; отдать один вердикт.

    Причину, по которой спросить не вышло, смотрят отдельные проверки: у
    остальных провайдер отвечает, и разбирать пару в каждой значило бы писать
    `[0]` в каждом тесте.
    """
    validation, _trouble = await asked(
        check, client, raw_text=raw_text, profile=profile, parsed=parsed
    )
    return validation
