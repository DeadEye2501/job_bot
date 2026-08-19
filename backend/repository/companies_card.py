"""Ведение записей о компаниях."""

import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.spellings import dedupe_first_wins
from backend.models import Company, Vacancy
from backend.payloads import CompanyDetail, str_list, text_or_none

from backend.repository.vacancies_common import PARSED_ONLY
from backend.repository.blacklist import rename_blacklist_marks
from backend.repository.blacklist_marks import (
    active_blacklist_value,
    preferred_blacklist_value,
)
from backend.repository.merging import concat_notes, load_merge_pair
from backend.repository.vacancies_life import repoint_vacancies

logger = logging.getLogger(__name__)


async def create_company(
    session: AsyncSession,
    *,
    name: str,
    website: str | None = None,
    aliases: list[str] | None = None,
    notes: str | None = None,
) -> Company:
    """Insert a new Company row. Raises if name is empty.

    Единственное место, где заводится строка компании: и по кнопке из окна,
    и сведением разобранной вакансии. Сайт готовит зовущий — конвейер не
    пускает в колонку ссылки на агрегаторы, окно кладёт введённое как есть.

    Unique constraint on ``company.name`` will surface as IntegrityError if
    the user tries to create a duplicate. Окно превращает его в сообщение
    человеку, конвейер — в два исхода сведения, поэтому здесь он не
    перехватывается.
    """
    normalized = (name or "").strip()
    if not normalized:
        raise ValueError("create_company: name is required")
    company = Company(
        name=normalized,
        aliases=typed_spellings(aliases),
        website=(website or None),
        notes=(notes or None),
    )
    session.add(company)
    await session.flush()
    logger.info(
        "Created company id=%d name=%r website=%s",
        company.id,
        normalized,
        website,
    )
    return company


def company_blacklist_candidates(co: Company) -> list[str]:
    """Possible blacklist `value` strings that should match this company.

    Just the company name — no other identifiers exist (no @username
    equivalent for companies). Returned as a list to mirror the HR helper
    so callers can use the same `value.in_(candidates)` shape.

    Написание одно, и оно же попадает в кнопку «в чёрный список»
    (см. `preferred_blacklist_value`).
    """
    return [co.name] if co.name else []


def company_blacklist_preferred_value(co: Company) -> str | None:
    return preferred_blacklist_value(company_blacklist_candidates(co))


async def _company_blacklist_value(
    session: AsyncSession, co: Company
) -> str | None:
    return await active_blacklist_value(
        session, "company", company_blacklist_candidates(co)
    )


async def get_company_detail(
    session: AsyncSession, company_id: int
) -> "CompanyDetail | None":
    """Detail payload for the Contacts/Companies pane (06): company row +
    vacancy count + distinct HR count + blacklist status.
    """
    co = await session.get(Company, company_id)
    if co is None:
        return None
    vacancy_count = int(
        await session.scalar(
            select(func.count(Vacancy.id)).where(
                Vacancy.company_id == company_id, PARSED_ONLY
            )
        )
        or 0
    )
    hr_count = int(
        await session.scalar(
            select(func.count(func.distinct(Vacancy.hr_id))).where(
                Vacancy.company_id == company_id,
                Vacancy.hr_id.is_not(None),
                PARSED_ONLY,
            )
        )
        or 0
    )
    blacklist_value = await _company_blacklist_value(session, co)
    return CompanyDetail(
        company=co,
        vacancy_count=vacancy_count,
        hr_count=hr_count,
        blacklist_value=blacklist_value,
    )


def add_company_spellings(co: Company, incoming: list) -> None:
    """Дописать компании написания, которых она ещё не знает.

    Занятыми считаются имя и нынешние написания, сравнение — без учёта
    регистра и без схлопывания разделителей: «Сбер-Тех» и «Сбер Тех» —
    разные написания, а схлопывающий ключ отвечает на другой вопрос, «та же
    ли это компания», и списку написаний он не судья. Сличи им — и второе
    написание не запомнилось бы, а список для того и копится.

    Обе стороны просеиваются `str_list`: колонка написаний — JSON, и что в
    ней лежит, код не обещает. Потерять негодное содержимое дешевле, чем
    уронить разбор вакансии или слияние, — строками оно всё равно не было.
    Отсеивается при этом только негодное: написание, равное имени компании,
    у лежащих остаётся — правка карточки не выбрасывает его нарочно, и
    вычищать набранное человеком тут незачем.

    Порознь эти два списка чистились по разным правилам, и одно и то же
    написание попадало в базу то обрезанным, то с пробелами.
    """
    known = {(co.name or "").casefold()}
    aliases = str_list(co.aliases)
    known.update(a.casefold() for a in aliases)
    co.aliases = aliases + dedupe_first_wins(
        str_list(incoming), str.casefold, known
    )


def typed_spellings(aliases) -> list[str]:
    """Набранные человеком написания, готовые лечь в колонку.

    Годные строки, обрезанные по краям, без повторов без учёта регистра. С
    именем компании набранное не сверяется намеренно: список человек пишет
    руками, и выбросить написанное им значило бы стереть введённое молча.
    Слияние и разбор вакансии сверяются — там список копится сам
    (`add_company_spellings`).

    Дороги сюда две, заведение и правка, и обе кладут в ту же колонку: пиши
    они чистку порознь, одно и то же написание попадало бы в базу по-разному
    в зависимости от того, каким окном его завели.
    """
    return dedupe_first_wins(str_list(aliases), str.casefold)


async def update_company_fields(
    session: AsyncSession, company_id: int, **fields
) -> bool:
    """Записать названные поля компании; неназванные остаются как были.

    Поля приходят набором, а не доводами: их четыре — `name`, `website`,
    `aliases`, `notes`, — и отдельными доводами вызов перевалил бы за предел
    правила 5. Отсутствие ключа и значит «не трогать», поэтому и метка
    «не задано» здесь не нужна: `None` в наборе — это «стереть».

    Ложь возвращается в двух случаях: компании с таким номером нет и имя
    задано пустым. Второй случай отменяет весь вызов, а не одно поле: имя
    обязательно и уникально, а соседние поля из того же вызова человек правил
    в одной форме — записать половину значило бы соврать окну об исходе.

    Отметка чёрного списка едет за именем (`rename_blacklist_marks`): она
    заведена на прежнее написание, и без переезда продолжила бы отсеивать
    посты, пропав из карточки.
    """
    co = await session.get(Company, company_id)
    if co is None:
        return False
    if "name" in fields:
        cleaned = str(fields["name"] or "").strip()
        if not cleaned:
            return False
        previous = co.name
        co.name = cleaned
        await rename_blacklist_marks(
            session, "company", old_value=previous, new_value=cleaned
        )
    if "website" in fields:
        co.website = text_or_none(fields["website"])
    if "aliases" in fields:
        co.aliases = typed_spellings(fields["aliases"])
    if "notes" in fields:
        co.notes = text_or_none(fields["notes"])
    await session.flush()
    logger.debug("Updated company %d fields=%s", company_id, sorted(fields))
    return True


async def delete_company(session: AsyncSession, company_id: int) -> bool:
    """Drop the company; vacancies survive with ``company_id = NULL``.

    Mirrors ``delete_hr``'s SET-NULL-on-vacancies stance: a vacancy is
    intrinsic to its source channel, not to the company tag we attached.
    Caller commits.
    """
    co = await session.get(Company, company_id)
    if co is None:
        return False
    co_name = co.name
    detached = await repoint_vacancies(
        session, Vacancy.company_id, absorbed_id=company_id, survivor_id=None
    )
    await session.delete(co)
    logger.info(
        "Deleted company %d (%r), detached %d vacancies",
        company_id,
        co_name,
        int(detached or 0),
    )
    return True


@dataclass(frozen=True, slots=True)
class _AbsorbedCompany:
    """Что уносится с поглощаемой компанией; читается до удаления строки."""

    name: str
    aliases: list
    website: str | None
    notes: str | None


def _carry_company_to_survivor(
    survivor: Company, taken: _AbsorbedCompany
) -> None:
    """Перенести на выжившую компанию то, что не пропадает с поглощённой.

    Имя поглощённой становится её написанием: по нему компанию продолжают
    искать словами. Сравнение буквальное, без нормализации имён: список
    написаний читает не только сопоставление (ему хватило бы нормализованных
    форм), но и поиск по подстроке, и карточка компании. Написание,
    отброшенное как «сопоставлению ничего не даёт», исчезло бы из базы вместе
    с поглощённой строкой.

    Сайт берётся, только если своего нет, а заметки склеиваются — иначе
    написанное человеком пропадало бы молча.
    """
    add_company_spellings(survivor, taken.aliases + [taken.name])
    if not survivor.website and taken.website:
        survivor.website = taken.website
    survivor.notes = concat_notes(survivor.notes, taken.notes)


async def merge_company(
    session: AsyncSession, *, absorbed_id: int, survivor_id: int
) -> None:
    """Merge ``absorbed`` company into ``survivor``. Irreversible.

    Caller must wrap in ``session.begin()``.
    """
    absorbed, survivor = await load_merge_pair(
        session,
        Company,
        absorbed_id=absorbed_id,
        survivor_id=survivor_id,
        subject="merge_company",
    )
    taken = _AbsorbedCompany(
        name=absorbed.name,
        aliases=list(absorbed.aliases or []),
        website=absorbed.website,
        notes=absorbed.notes,
    )
    moved_vacancies = await repoint_vacancies(
        session,
        Vacancy.company_id,
        absorbed_id=absorbed_id,
        survivor_id=survivor_id,
    )
    await session.delete(absorbed)
    await session.flush()
    _carry_company_to_survivor(survivor, taken)
    await rename_blacklist_marks(
        session, "company", old_value=taken.name, new_value=survivor.name
    )

    logger.info(
        "merged company #%d -> #%d (vacancies=%d)",
        absorbed_id, survivor_id, moved_vacancies,
    )
