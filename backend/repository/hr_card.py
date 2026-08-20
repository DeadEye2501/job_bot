"""Одна запись HR: чтение, правка, слияние, удаление."""

import logging
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.domain.telegram_identity import typed_username
from backend.models import Company, HR, Message, Vacancy
from backend.payloads import HrDetail
from backend.incoming import text_or_none

from backend.repository.blacklist import rename_blacklist_marks
from backend.repository.blacklist_marks import (
    account_mark,
    active_blacklist_value,
    nickname_mark,
    preferred_blacklist_value,
)
from backend.repository.merging import concat_notes, load_merge_pair
from backend.repository.vacancies_life import repoint_vacancies
from backend.repository.messages import UNREAD_INCOMING

logger = logging.getLogger(__name__)


LAST_VACANCY_ORDER = (Vacancy.created_at.desc(), Vacancy.id.desc())
"""Порядок «самая свежая вакансия человека», по которому берут его компанию.

Одно объявление на карточку и на список: спрашивают они одно и то же, а
приёмы разные — карточке хватает одной строки с ограничением, списку нужна
оконная нумерация по всем людям разом. Разойдись порядки, два экрана называли
бы разные компании, и заметить это было бы нечем.

Разрешитель по идентификатору не украшение: время заведения проставляет база
одним `CURRENT_TIMESTAMP`, и две вакансии подряд легко получают одну метку.

Свежую вакансию без компании оба читают одинаково — как «компании нет»:
важно, с кем человек работает сейчас, а не с кем работал когда-то.

Свежесть здесь — **наша**: когда строка завелась у нас. Соседний
`vacancies_common.VACANCY_APPEARED_AT` меряет прежде всего чужую — когда
вышел пост, — и падает на нашу, только если времени поста нет вовсе.
Подменять одну другой нельзя: пост мог выйти в понедельник, а завестись в
пятницу. Той свежестью пользуются атрибуция ответа HR
(`hr_identify.find_latest_vacancy_id_for_hr`, она сверяется со временем
письма из Telegram) и мини-список канала.
"""


async def update_hr_fields(session: AsyncSession, hr_id: int, **fields) -> bool:
    """Записать названные поля человека; неназванные остаются как были.

    Поля приходят набором, а не доводами — тем же образом, что у компании:
    отсутствие ключа и значит «не трогать», а `None` в наборе — «стереть».
    Пустая строка сводится к пустоте: схема не различает «нет» и «пусто».

    Имена полей набора никто здесь не сверяет: набирает его мост, отбирая
    известные ключи из нагрузки окна, и незнакомому взяться неоткуда.

    Ник разбирается тем же объявлением, что и при заведении: правка того же
    поля не может принимать то, что форма заведения отвергает. Не
    телеграмовское роняет ``ValueError`` — прежний ник при этом остаётся
    цел, а молча записанное имя человека обнаружилось бы только тогда,
    когда отправка перестала находить собеседника.

    Ложь возвращается, только если человека с таким номером нет. Транзакцию
    закрывает зовущий.
    """
    hr = await session.get(HR, hr_id)
    if hr is None:
        return False
    if "name" in fields:
        hr.name = text_or_none(fields["name"])
    if "telegram_username" in fields:
        typed = fields["telegram_username"]
        hr.telegram_username = None if typed is None else typed_username(typed)
    if "notes" in fields:
        hr.notes = text_or_none(fields["notes"])
    await session.flush()
    logger.debug("Updated HR %d fields=%s", hr_id, sorted(fields))
    return True


async def _last_company_of(
    session: AsyncSession, hr_id: int
) -> tuple[int | None, str | None]:
    """Компания последней вакансии человека — номер и имя.

    Соединение внешнее: последняя вакансия могла быть без компании, и тогда
    у карточки нет её ни номером, ни именем. Порядок — общий
    `LAST_VACANCY_ORDER`: разойдись он со списком, карточка и перечень
    называли бы разные компании.
    """
    row = (
        await session.execute(
            select(Company.id, Company.name)
            .select_from(Vacancy)
            .outerjoin(Company, Company.id == Vacancy.company_id)
            .where(Vacancy.hr_id == hr_id)
            .order_by(*LAST_VACANCY_ORDER)
            .limit(1)
        )
    ).first()
    return (row[0], row[1]) if row else (None, None)


async def _unread_count_of(session: AsyncSession, hr_id: int) -> int:
    """Сколько непрочитанных входящих у человека."""
    return int(
        await session.scalar(
            select(func.count(Message.id)).where(
                Message.hr_id == hr_id,
                *UNREAD_INCOMING,
            )
        )
        or 0
    )


async def get_hr_detail(
    session: AsyncSession, hr_id: int
) -> HrDetail | None:
    """Detail payload for the Contacts / HR pane (05).

    Returns the HR row + компания с самой свежей его вакансии (id + name,
    порядок — `LAST_VACANCY_ORDER`; пусто, если та вакансия ни к какой
    компании не привязана) + count of unread incoming messages. Returns
    ``None`` if the HR row is gone.

    Счёта вакансий здесь нет: карточка его не показывала, а считался он
    запросом на каждое её открытие. Число, которое человек видит, приезжает
    строкой перечня.
    """
    hr = await session.get(HR, hr_id)
    if hr is None:
        return None
    last_company_id, last_company_name = await _last_company_of(session, hr_id)
    return HrDetail(
        hr=hr,
        last_company_id=last_company_id,
        last_company_name=last_company_name,
        unread_count=await _unread_count_of(session, hr_id),
        blacklist_value=await hr_blacklist_value(session, hr),
    )


def _marks_of(user_id: int | None, username: str | None) -> list[str]:
    """Написания отметки по паре опознаний — живой карточки или её снимка.

    Снимок нужен слиянию: там написания читают до удаления строки, а карточки
    уже нет. Написание отметки не зависит больше ни от чего, поэтому оба зовут
    одно.
    """
    out: list[str] = []
    if user_id is not None:
        out.append(account_mark(user_id))
    if username:
        out.append(nickname_mark(username))
    return out


def hr_blacklist_candidates(hr: HR) -> list[str]:
    """Написания, под которыми человек может числиться в чёрном списке.

    Проверяются оба: строку заводили и тогда, когда у карточки был один ник,
    и тогда, когда один номер. Совпадение ищется точное, по нынешним
    написаниям карточки, — то есть отметка, заведённая под ником, потеряется,
    если ник у карточки сменится и старого написания в перечне не станет.

    Порядок значим: первое написание — то, что запишет кнопка «в чёрный
    список» (см. `preferred_blacklist_value`), и первым стоит несменяемый
    номер учётной записи. Ник Telegram отдаёт заново с каждым входящим, и
    карточка его перезаписывает: отметка на нём слетает молча, а строка в
    списке продолжает гореть.
    """
    return _marks_of(hr.telegram_user_id, hr.telegram_username)


async def hr_blacklist_value(session: AsyncSession, hr: HR) -> str | None:
    return await active_blacklist_value(session, "hr", hr_blacklist_candidates(hr))


async def delete_hr(session: AsyncSession, hr_id: int) -> bool:
    """Cascade-delete the HR row. Caller commits.

    Messages are removed (chat history is meaningless without the HR);
    vacancies survive with ``hr_id`` set to NULL — they're intrinsic to
    their source channel, not to who messaged us about them. Returns
    ``True`` if the HR existed and was removed, ``False`` if not found.
    """
    hr = await session.get(HR, hr_id)
    if hr is None:
        return False
    hr_label = hr.name or hr.telegram_username
    msgs_deleted = (
        await session.execute(delete(Message).where(Message.hr_id == hr_id))
    ).rowcount
    detached = await repoint_vacancies(
        session, Vacancy.hr_id, absorbed_id=hr_id, survivor_id=None
    )
    await session.delete(hr)
    logger.info(
        "Deleted HR %d (%r), messages purged=%d, vacancies detached=%d",
        hr_id,
        hr_label,
        int(msgs_deleted or 0),
        int(detached or 0),
    )
    return True


@dataclass(frozen=True, slots=True)
class _AbsorbedHr:
    """Что уносится с поглощаемым человеком.

    Снимок читается **до** удаления строки: после него обращение к полям
    удалённой записи — уже не чтение, а поведение сессии.

    Два написания учётной записи здесь те же, что у карточки, и `_marks_of`
    читает их снимком наравне с ней: написание отметки зависит только от них.
    """

    telegram_user_id: int | None
    telegram_username: str | None
    name: str | None
    notes: str | None


async def _drop_letters_the_survivor_already_has(
    session: AsyncSession, absorbed_id: int, survivor_id: int
) -> int:
    """Убрать у поглощаемого письма, что уже есть у выжившего; сколько убрали.

    Две карточки одного человека — это одна переписка Telegram, и номера
    писем у них общие: наша отправка легла под ту карточку, из чата которой
    её послали, а её эхо — под ту, которую нашло опознание. Переезд такого
    письма упирается в `uq_message_hr_tgid_dir`, и сделка слияния
    откатывается целиком — вместе с переездом вакансий.

    Своя строка выжившего при этом выигрывает: она уже связана с его
    вакансией, а вакансия — то, ради чего переписку и читают. Цена известна:
    отметка о прочтении держится на сносимой строке — её ставят по номеру
    учётной записи, то есть поглощаемому, — и вторая галочка у письма гаснет
    до ближайшего оповещения из Telegram.
    """
    kept = aliased(Message)
    twin = (
        select(kept.id)
        .where(
            kept.hr_id == survivor_id,
            kept.tg_message_id == Message.tg_message_id,
            kept.is_incoming == Message.is_incoming,
        )
        .exists()
    )
    dropped = await session.execute(
        delete(Message).where(Message.hr_id == absorbed_id, twin)
    )
    return dropped.rowcount or 0


async def _move_or_drop_chat(
    session: AsyncSession, absorbed_id: int, survivor_id: int,
    survivor_has_tg: bool,
) -> tuple[int, int]:
    """Переписка поглощаемого: перенести или стереть. Сколько того и другого.

    Учётная запись Telegram и переписка ходят вместе: у выжившего своя
    запись — чужая переписка стирается вместе с ней, нет своей — переписка
    переезжает на него целиком.
    """
    if survivor_has_tg:
        dropped = (
            await session.execute(
                delete(Message).where(Message.hr_id == absorbed_id)
            )
        ).rowcount or 0
        return 0, dropped
    dropped = await _drop_letters_the_survivor_already_has(
        session, absorbed_id, survivor_id
    )
    moved = (
        await session.execute(
            update(Message)
            .where(Message.hr_id == absorbed_id)
            .values(hr_id=survivor_id)
        )
    ).rowcount or 0
    return moved, dropped


def _carry_to_survivor(
    survivor: HR, taken: _AbsorbedHr, survivor_has_tg: bool
) -> None:
    """Перенести на выжившего то, что не пропадает вместе с поглощённым.

    Учётная запись Telegram достаётся только тому, у кого своей не было —
    вместе с перееханной перепиской. Один ник учётной записью не считается:
    без числового идентификатора это ручная подсказка, а не аккаунт. Имя
    берётся, только если у выжившего пусто, а заметки склеиваются — иначе
    написанное человеком пропадало бы молча.
    """
    if not survivor_has_tg:
        if taken.telegram_user_id is not None:
            survivor.telegram_user_id = taken.telegram_user_id
        if taken.telegram_username:
            survivor.telegram_username = taken.telegram_username
    if not survivor.name and taken.name:
        survivor.name = taken.name
    survivor.notes = concat_notes(survivor.notes, taken.notes)


async def _carry_marks_to_survivor(
    session: AsyncSession, written_before: list[str], survivor: HR
) -> None:
    """Перевести отметки на нынешнее написание выжившего.

    Написания меняются с обеих сторон: у поглощённого учётная запись
    пропадает, а у выжившего её, наоборот, может заместить чужая — тогда
    осиротеет уже его собственная отметка. Поэтому переводится всё, что
    перестало быть написанием выжившего, а не только написания поглощённого.

    Останься отметка на пропавшем написании — заслон отправки перестал бы
    видеть отсеянного человека, бот написал бы заблокированному, а строка
    списка продолжила бы отсеивать посты по чужому теперь нику. Так же это
    устроено у компании, где отметка едет за именем.

    Написание выжившего берётся то же, что пишет кнопка: у него их бывает
    два, и разойдись выбор — отметка встала бы на второе, а карточка искала
    бы по первому.
    """
    now = hr_blacklist_candidates(survivor)
    survivor_value = preferred_blacklist_value(now)
    if survivor_value is None:
        return
    for old_value in written_before:
        if old_value not in now:
            await rename_blacklist_marks(
                session, "hr", old_value=old_value, new_value=survivor_value
            )


async def merge_hr(
    session: AsyncSession, *, absorbed_id: int, survivor_id: int
) -> None:
    """Merge ``absorbed`` HR into ``survivor``. Irreversible.

    Caller must wrap in ``session.begin()``. Вакансии объединяются, а что
    делается с учётной записью, перепиской, именем, заметками и отметкой
    чёрного списка — см. :func:`_move_or_drop_chat`, :func:`_carry_to_survivor`
    и :func:`_carry_marks_to_survivor`.
    """
    absorbed, survivor = await load_merge_pair(
        session,
        HR,
        absorbed_id=absorbed_id,
        survivor_id=survivor_id,
        subject="merge_hr",
    )
    taken = _AbsorbedHr(
        telegram_user_id=absorbed.telegram_user_id,
        telegram_username=absorbed.telegram_username,
        name=absorbed.name,
        notes=absorbed.notes,
    )
    survivor_has_tg = survivor.telegram_user_id is not None
    # Написания обеих карточек читаются до переноса полей: после него часть
    # из них уже не написания выжившего, и отличить пропавшие будет нечем.
    written_before = hr_blacklist_candidates(survivor) + _marks_of(
        taken.telegram_user_id, taken.telegram_username
    )

    moved_vacancies = await repoint_vacancies(
        session, Vacancy.hr_id, absorbed_id=absorbed_id, survivor_id=survivor_id
    )
    moved_messages, dropped_messages = await _move_or_drop_chat(
        session, absorbed_id, survivor_id, survivor_has_tg
    )
    await session.delete(absorbed)
    await session.flush()
    _carry_to_survivor(survivor, taken, survivor_has_tg)
    await _carry_marks_to_survivor(session, written_before, survivor)

    logger.info(
        "merged HR #%d -> #%d (vacancies=%d, messages moved=%d, dropped=%d)",
        absorbed_id, survivor_id, moved_vacancies, moved_messages, dropped_messages,
    )
