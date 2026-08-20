"""Короткие списки вакансий для карточек других предметов."""

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Vacancy, VacancyStatus
from backend.repository.hr_card import LAST_VACANCY_ORDER
from backend.repository.paging import trim_page
from backend.repository.vacancies_common import PARSED_ONLY, VACANCY_APPEARED_AT

# Обещание этого порядка — «по ходу воронки»: наверху офер, под ним «в
# процессе», и только потом приглашение с тестом. Так потому, что по графу
# авто-переходов в «в процессе» приходят только из них (`domain/transitions.py`;
# рукой человек ставит любой статус из любого, граф ему не указ) — значит,
# зашло дальше. Внизу холодное, и «не подходит» последним: это наш собственный
# отсев, а не чужой ответ.
#
# У большого списка (`vacancies_list.py`) обещание другое — воронка с конца с
# поднятыми тестом и приглашением, — и холодный хвост там свой, «не подходит»
# идёт первым. Расхождение подтверждено человеком 19.08 и намеренно: сводить
# таблицы в одну не надо.
#
# Secondary sort внутри одного статуса — по дате появления вакансии
# (posted_at если есть, иначе created_at), новые сверху.
#
# Ключи — .value-строки, а не enum-члены: при `case(dict, value=col)` SA
# биндит ключи как литералы БЕЗ прогона через Enum-type processor колонки,
# и aiosqlite падает с `type 'VacancyStatus' is not supported`. Падение
# проглатывалось диспетчером прежнего окна, и мини-список рендерил «нет
# вакансий», хотя badge/funnel показывали реальный count.
_CHANNEL_VAC_STATUS_RANK: dict[str, int] = {
    VacancyStatus.OFFER.value: 1,
    VacancyStatus.IN_PROGRESS.value: 2,
    VacancyStatus.INVITATION.value: 3,
    VacancyStatus.TEST.value: 4,
    VacancyStatus.ANSWERED.value: 5,
    VacancyStatus.APPLIED.value: 6,
    VacancyStatus.NEW.value: 7,
    VacancyStatus.SCAM.value: 8,
    VacancyStatus.GHOSTING.value: 9,
    VacancyStatus.DECLINE.value: 10,
    VacancyStatus.NOT_FIT.value: 11,
}


async def _list_linked(session: AsyncSession, linked_to) -> list[Vacancy]:
    """Разобранные вакансии, привязанные к предмету, свежими вперёд.

    Недоразобранные не показываются: строка, оставшаяся от прерванного
    прогона, в списке карточки выглядела бы пустой.

    Свежесть здесь наша, время заведения (`hr_card.LAST_VACANCY_ORDER`), и
    порядок один с карточкой человека — иначе список и карточка называли бы
    разные компании. Список канала ниже сортируется прежде всего по горячести
    статуса, а свежестью разрешает равных — и свежесть там чужая, время выхода
    поста: канал человек узнаёт по датам публикаций, а не по тому, когда до
    них добрался бот.
    """
    rows = (
        await session.scalars(
            select(Vacancy)
            .where(linked_to, PARSED_ONLY)
            .order_by(*LAST_VACANCY_ORDER)
        )
    ).all()
    return list(rows)


async def list_vacancies_for_hr(
    session: AsyncSession,
    hr_id: int,
) -> list[Vacancy]:
    """All parsed vacancies for an HR, newest-first. Powers the «список
    вакансий» mini-list in the Contacts/HR detail pane.
    """
    return await _list_linked(session, Vacancy.hr_id == hr_id)


async def list_vacancies_for_company(
    session: AsyncSession, company_id: int
) -> list[Vacancy]:
    """All parsed vacancies linked to this company, newest-first."""
    return await _list_linked(session, Vacancy.company_id == company_id)


async def count_vacancies_for_channel(session: AsyncSession, channel_id: int) -> int:
    """Сколько разобранных вакансий числится за каналом.

    Отбор тот же, что у списка рядом и у счётчика в карточке: мост сверяет с
    этим числом пустую страницу и жалуется на расхождение. Считай оно иначе —
    жалоба приходила бы на всякий канал, у которого есть хоть одна
    недоразобранная строка, то есть на любой работающий.
    """
    counted = await session.execute(
        select(func.count(Vacancy.id)).where(
            Vacancy.source_channel_id == channel_id, PARSED_ONLY
        )
    )
    return int(counted.scalar_one())


async def list_vacancies_for_channel(
    session: AsyncSession,
    channel_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Vacancy], bool]:
    """Страница разобранных вакансий канала и есть ли за ней ещё.

    Порядок — по горячести статуса, потом по свежести. Страница нужна потому,
    что каналы накапливают тысячи вакансий, и мини-список карточки грузит их
    пачками; признак продолжения отдаёт запрос — см. `paging.trim_page`.

    Недоразобранные не показываются — тем же отбором, что берут счётчик
    канала и его числа: все трое обещают выдачу, и разойдись они, число в
    пилюле перестало бы отвечать за список под ней.
    """
    status_rank = case(
        _CHANNEL_VAC_STATUS_RANK,
        value=Vacancy.status,
        else_=99,
    )
    rows = (
        await session.scalars(
            select(Vacancy)
            .where(Vacancy.source_channel_id == channel_id, PARSED_ONLY)
            .order_by(
                status_rank.asc(),
                VACANCY_APPEARED_AT.desc(),
                Vacancy.id.desc(),
            )
            .limit(limit + 1)
            .offset(offset)
        )
    ).all()
    return trim_page(list(rows), limit)
