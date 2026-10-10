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
from backend.repository.hr_card import hr_blacklist_value

NO_TARGET = "нет адресата"
BLACKLISTED = "чёрный список"
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

    Режима среди заслонов нет: он про автоматику и решает, запускать ли её, а
    сюда приходят и автоматика, и человек. Автоматика при выключенном режиме
    сюда не доходит — её не запускают, — а нажатое человеком уходит в любом.

    Порядок стоит по цене: адресат читается из того, что уже под рукой, чёрный
    список — единственный, кто идёт в базу, и потому стоит за ним. Замок
    отправки последний: он снимается одним переключателем, а всё, что выше,
    пользователь чинит по-настоящему — и узнать об этом ему полезнее.
    """
    target = telegram_peer(hr)
    if target is None:
        return SendPermission(refusal=NO_TARGET)
    async with bot.session_factory() as session:
        blacklisted = await hr_blacklist_value(session, hr)
    if blacklisted:
        return SendPermission(
            target=target, refusal=BLACKLISTED, blacklist_value=blacklisted
        )
    if telegram.SEND_LOCKED:
        return SendPermission(target=target, refusal=SENDING_LOCKED)
    return SendPermission(target=target)
