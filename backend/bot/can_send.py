"""Один ответ на вопрос «можно ли писать этому HR» — окну и конвейеру.

Спрашивают его двое: отправка отклика и переписка из окна. Разъехаться им
нельзя — тогда на одном и том же HR они называют разные причины, и человек
по подсказке чинит не то, что мешает. А вот что делать с ответом, каждый
решает сам: окну нужен текст отказа, конвейеру — отметка в журнале.

Причина отдаётся словом, а не готовой фразой: у окна и у журнала разный
язык, и общая фраза не подошла бы ни тому, ни другому.
"""

from dataclasses import dataclass

from adapters import telegram
from backend.domain.telegram_identity import telegram_peer
from backend.models import BotMode
from backend.repository.hr_card import _hr_blacklist_value

NO_TARGET = "нет адресата"
BOT_OFF = "бот выключен"
BLACKLISTED = "чёрный список"
DRY_RUN = "тестовый режим"
SENDING_LOCKED = "отправка заглушена"


@dataclass(frozen=True)
class SendPermission:
    """Кому писать и почему нельзя. Пустая причина — можно."""

    target: int | str | None = None
    refusal: str | None = None
    # Причина попадания в чёрный список: окно показывает её человеку, чтобы
    # тот знал, откуда снимать отметку.
    blacklist_value: str | None = None


async def can_send_to_hr(bot, hr) -> SendPermission:
    """Проверяет заслоны по порядку и отдаёт первый сработавший.

    Порядок стоит по цене: адресат и режим читаются из того, что уже под
    рукой, чёрный список — единственный, кто идёт в базу, и потому стоит за
    ними. Замки последние: они снимаются одним переключателем, а всё, что
    выше, пользователь чинит по-настоящему — и узнать об этом ему полезнее.
    """
    target = telegram_peer(hr)
    if target is None:
        return SendPermission(refusal=NO_TARGET)
    if (await bot._current_mode()) is BotMode.OFF:
        return SendPermission(target=target, refusal=BOT_OFF)
    async with bot._session_factory() as session:
        blacklisted = await _hr_blacklist_value(session, hr)
    if blacklisted:
        return SendPermission(
            target=target, refusal=BLACKLISTED, blacklist_value=blacklisted
        )
    if bot._dry_run:
        return SendPermission(target=target, refusal=DRY_RUN)
    if telegram.SEND_LOCKED:
        return SendPermission(target=target, refusal=SENDING_LOCKED)
    return SendPermission(target=target)
