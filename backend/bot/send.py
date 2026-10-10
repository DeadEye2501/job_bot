"""Доставка отклика в Telegram: вложение, ограничения сервиса, след в базе."""

import logging
from dataclasses import dataclass

from adapters import telegram
from backend.bot import can_send
from backend.models import HR
from backend.payloads import OutgoingMessage
from backend.flows.events import record_vacancy_event
from backend.notify import fire
from backend.repository.messages import save_outgoing_message
from backend.telegram_time import utc_now
from backend.repository.vacancy_status import mark_vacancy_applied

logger = logging.getLogger(__name__)


def _applied_label(force: bool) -> str:
    """Чем подписан перевод в «отклик отправлен» в истории вакансии."""
    return "Ручная отправка." if force else "Авто-отправка отклика."


def _shares_provider(a, b) -> bool:
    """Two LLM provider configs share the same httpx client if endpoint+auth match.

    Model name is intentionally NOT compared — model is per-request, not on
    the client.
    """
    return (
        a is not None
        and b is not None
        and a.base_url == b.base_url
        and a.api_key == b.api_key
    )


async def ui_send_vacancy_application(bot, vacancy_id: int) -> tuple[bool, str]:
    """Manual cover-letter send — vacancy detail «more» menu, кнопка
    «Отправить отклик». Возвращает (ok, reason) — UI использует reason
    для понятного toast'а (что именно не сработало)."""
    logger.info("UI send application for vacancy %d", vacancy_id)
    return await bot.ingestion.send_application_for_vacancy(vacancy_id)


@dataclass(frozen=True, slots=True)
class Errand:
    """По какому поводу шлём письмо: вакансия и настойчивость.

    Пара, а не два довода: оба говорят об одном — откуда взялась отправка.
    Ручная (`force`) отличается от самоотклика только тем, что переход статуса
    ей разрешён поверх графа, и без номера вакансии это ничего не значит.
    Разложенные доводами, они дают у отправки шесть штук — линт краснеет, а
    зовущий путает местами два необязательных.
    """

    vacancy_id: int | None = None
    force: bool = False


@dataclass(frozen=True, slots=True)
class _Outcome:
    """Чем кончилась отправка — то, что после неё надо записать.

    Четыре значения ходят вместе от самой отправки до строки в ленте:
    номер вакансии, номер письма в Telegram, признак заглушки и признак
    ручной отправки. Порознь ни одно из них не значит ничего: по номеру
    письма пишется строка переписки, по заглушке решается, писать ли её
    вовсе, а признак ручной отправки решает, пропускать ли переход статуса
    поверх графа.
    """

    vacancy_id: int | None
    tg_message_id: int | None
    suppressed: bool
    force: bool


async def _note_flood_wait(bot, error) -> None:
    """Запомнить, до какого времени Telegram просил не писать.

    Запись переживает перезапуск нарочно: автоотправка спрашивает её перед
    каждым откликом и молчит, пока окно не закроется. Ручной отправке из
    окна это просто отказ — человек увидит подсказку и попробует позже.
    """
    import time as _time

    secs = int(getattr(error, "value", 0) or 0)
    logger.warning("Bot.send: FloodWait %d сек, persist'у flood_wait_until_ts", secs)
    try:
        await bot.rs.set_app("flood_wait_until_ts", str(_time.time() + secs))
    except Exception:
        logger.exception("Bot.send: failed to persist flood_wait_until_ts")


async def _clear_flood_wait(bot) -> None:
    """Снять запрет: Telegram отпустил, и ждать больше нечего.

    Не сняв его, автоотправка после восстановления сверялась бы с
    просроченным окном и молчала бы дольше, чем просили.
    """
    if bot.rs.flood_wait_until_ts <= 0:
        return
    try:
        await bot.rs.set_app("flood_wait_until_ts", "0")
    except Exception:
        logger.exception("Bot.send: failed to clear flood_wait_until_ts")


async def _deliver_dm(
    bot, target, text: str, attachment, vacancy_id
) -> tuple[int | None, bool]:
    """Отдать письмо Telegram; отдать его номер и можно ли считать дело сделанным.

    Отказ по частоте — единственный, после которого продолжать нельзя:
    письма нет, и зачесть отклик значило бы закрыть вакансию от следующей
    попытки навсегда. Текст письма в журнал не идёт — в нём имя,
    работодатели и навыки из анкеты.
    """
    from pyrogram.errors import FloodWait

    logger.info(
        "Sending DM to hr %s (vacancy=%s, %d chars)", target, vacancy_id, len(text)
    )
    try:
        tg_msg_id = await telegram.send_dm(bot.client, target, text, attachment)
    except FloodWait as e:
        await _note_flood_wait(bot, e)
        return None, False
    await _clear_flood_wait(bot)
    return tg_msg_id, True


async def _commit_send(bot, hr: HR, text: str, outcome: _Outcome) -> bool:
    """Записать следствия ушедшего письма; сказать, удалось ли записать.

    Строка переписки под заглушкой не пишется нарочно: номера сообщения в
    Telegram не существует, и строка с пустым номером показала бы в окне
    письмо, которого HR не получал. След заглушки остаётся отметкой в ленте.

    В подпись перевода статуса заглушка не дописывается по той же причине,
    по которой не пишется строка: запись в истории обязана быть одинаковой
    на тестовом стенде и в бою, иначе две базы читаются по-разному.

    Зов репозитория идёт первым в сделке нарочно: на повторе он откатывает
    сессию, а другой незакрытой работы к этому мигу быть не должно. Повтор
    здесь — выигранная эхом гонка, и его строка вакансии не знает вовсе.
    Дописываем: без привязки счётчик недавних писем вернёт ноль, и следующее
    обращение к тому же HR уйдёт полным письмом с резюме вместо короткого
    догона, а ответ HR отнесётся не к той вакансии.
    """
    async with bot.session_factory() as session:
        if not outcome.suppressed:
            stored, _ = await save_outgoing_message(
                session,
                OutgoingMessage(
                    hr_id=hr.id,
                    text=text,
                    tg_message_id=outcome.tg_message_id,
                    sent_at=utc_now(),
                    vacancy_id=outcome.vacancy_id,
                ),
            )
            stored.vacancy_id = outcome.vacancy_id
        applied_now = False
        if outcome.vacancy_id is not None:
            applied_now = await mark_vacancy_applied(
                session,
                outcome.vacancy_id,
                _applied_label(outcome.force),
                force=outcome.force,
            )
        await session.commit()
    return applied_now


def _log_refusal(permission, hr: HR, vacancy_id: int | None) -> None:
    """Записать отказ заслона: кому не написали и почему."""
    logger.warning(
        "Bot.send: %s (hr=%s, адресат=%s, чёрный список=%s, vacancy=%s)",
        permission.refusal, hr.id, permission.target,
        permission.blacklist_value, vacancy_id,
    )


async def _flip_applied_alone(bot, outcome: _Outcome) -> None:
    """Перевести вакансию в «откликнулись» отдельной тонкой сделкой.

    Зовётся, когда письмо уже ушло, а запись следствий сорвалась. Строку
    аудита в этом случае теряем, зато повторная отправка отобьётся обычной
    проверкой «уже откликались» — а она смотрит на статус.
    """
    if outcome.vacancy_id is None:
        return
    try:
        async with bot.session_factory() as session:
            if await mark_vacancy_applied(
                session,
                outcome.vacancy_id,
                _applied_label(outcome.force),
                force=outcome.force,
            ):
                await session.commit()
                logger.info(
                    "vacancy %s status -> APPLIED via fallback "
                    "(audit Message-row missing)",
                    outcome.vacancy_id,
                )
    except Exception:
        logger.exception(
            "Bot.send: fallback status-flip also FAILED for "
            "vacancy=%s — re-send protection broken, watch out",
            outcome.vacancy_id,
        )


async def _hand_over(
    bot, permission, text: str, attachment, vacancy_id
) -> tuple[int | None, bool]:
    """Отдать письмо Telegram или сымитировать отправку под замком.

    Имитация нужна затем, что иначе конвейер нельзя было бы обкатать без
    живых HR: всё, кроме самого вызова Telegram, идёт как при отправке.

    **Условие входа:** уцелевший отказ здесь означает замок и только его —
    незнакомые отказы зовущий отбил раньше. Текст письма в журнал не идёт
    ни на одной из двух дорог: в нём имя, работодатели и навыки из анкеты.
    """
    if permission.refusal is not None:
        logger.warning(
            "[%s] would have sent DM to %s (vacancy=%s, %d chars, attachment=%s)",
            permission.refusal, permission.target, vacancy_id, len(text), attachment,
        )
        return None, True
    return await _deliver_dm(bot, permission.target, text, attachment, vacancy_id)


async def _audit_sent(bot, hr_id: int, chars: int, outcome: _Outcome) -> None:
    """Отметить в ленте вакансии, что отклик ушёл.

    Без этой строки у человека остаются только письмо в переписке и
    сменившийся статус — а «отклик отправлен» отдельной строкой в истории
    не видно. Ручная отправка помечается своим признаком.
    """
    if outcome.vacancy_id is None:
        return
    await record_vacancy_event(
        bot.session_factory,
        outcome.vacancy_id,
        "applied_sent",
        {
            "hr_id": hr_id,
            "force": outcome.force,
            "suppressed": outcome.suppressed,
            "cover_letter_chars": chars,
            "tg_message_id": outcome.tg_message_id,
        },
    )


async def _record_send(bot, hr: HR, text: str, outcome: _Outcome, permission) -> None:
    """Записать следствия ушедшего письма, пережив беду записи.

    Отыгрывать нечего: письмо у HR. Поэтому сорвавшаяся запись не поднимается
    выше — статус переводится отдельной короткой сделкой, и только он удержит
    повторную отправку тому же человеку.
    """
    try:
        applied_now = await _commit_send(bot, hr, text, outcome)
    except Exception:
        logger.exception(
            "Bot.send: запись следствий сорвалась после%s отправки к %s "
            "(vacancy=%s, %d знаков); письмо ушло, строки переписки нет. "
            "Перевожу статус отдельно, чтобы отбить повторную отправку.",
            " заглушённой" if outcome.suppressed else "",
            permission.target, outcome.vacancy_id, len(text),
        )
        await _flip_applied_alone(bot, outcome)
        return
    if applied_now:
        logger.info("vacancy %s status -> APPLIED after send", outcome.vacancy_id)
    await _audit_sent(bot, hr.id, len(text), outcome)


async def send(
    bot, hr: HR, text: str, attachment=None, errand: Errand = Errand(),
) -> bool:
    """Отправить отклик HR; сказать, считать ли отклик сделанным.

    Отказ значит, что вакансия остаётся открытой для следующей попытки: нет
    адреса, чёрный список, Telegram попросил подождать.
    Заглушка отказом не считается — при ней состоялось всё, кроме вызова."""
    # Заслоны те же, что у переписки из окна: одно объявление на двоих.
    # Заглушает отправку ровно один замок, и назван он поимённо: незнакомая
    # причина — заведённая позже, и зачесть по ней отклик значило бы закрыть
    # вакансию от следующей попытки навсегда. Умолчание тут — отказ.
    permission = await can_send.can_send_to_hr(bot, hr)
    suppressed = permission.refusal == can_send.SENDING_LOCKED
    if permission.refusal is not None and not suppressed:
        _log_refusal(permission, hr, errand.vacancy_id)
        return False
    tg_msg_id, delivered = await _hand_over(
        bot, permission, text, attachment, errand.vacancy_id
    )
    if not delivered:
        return False
    # С этого момента письмо у HR (или сымитировано), и отсюда «сделано» уже
    # не зависит от того, чем кончилась запись: повторять отправку нельзя.
    await _record_send(
        bot,
        hr,
        text,
        _Outcome(errand.vacancy_id, tg_msg_id, suppressed, errand.force),
        permission,
    )
    # Окно узнаёт об отправке только этой вестью: зов, которым её завели,
    # ответил «пущено» задолго до того, как модель сочинила письмо.
    if errand.vacancy_id is not None:
        fire(bot.on_vacancies_changed, "on_vacancies_changed")
    return True
