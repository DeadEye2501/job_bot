"""Вакансия чужого профиля: на экранах её нет, в карточках она внизу.

Активен профиль 1, чужие вакансии лежат в профиле 2; HR, компании и
источники общие.
"""

from backend.models import VacancyStatus
from backend.models.settings import CHANNEL_KIND
from backend.repository.aggregators import list_aggregators_with_counts
from backend.repository.channels import get_channel_detail, list_telegram_channels
from backend.repository.companies_list import list_companies_with_counts
from backend.repository.hr_list import list_hr_with_counts, list_hrs_for_company
from backend.repository.stats_kpi import get_stats_kpi
from backend.repository.stats_pipeline import get_stats_channels_pipeline
from backend.repository.stats_responses import get_stats_hr_responses
from backend.repository.stats_statuses import get_stats_status_breakdown
from backend.repository.vacancies_list import list_vacancy_filter_options
from backend.repository.vacancies_mini import (
    list_vacancies_for_company,
    list_vacancies_for_hr,
    list_vacancies_from,
)
from tests.backend.fixtures.stats import rows_by_channel
from tests.dbio import put, put_other_workspace
from tests.factories import (
    OTHER_WORKSPACE_ID,
    at,
    channel_row,
    company_row,
    days_ago,
    hr_row,
    status_history_row,
    trash_event_row,
    vacancy_row,
)
from tests.factories_aggregators import aggregator_row


async def test_the_list_shows_only_the_active_workspace(titles, session_factory):
    await put_other_workspace(session_factory)
    await put(
        session_factory,
        vacancy_row(title="Своя"),
        vacancy_row(title="Чужая", workspace_id=OTHER_WORKSPACE_ID),
    )

    assert await titles() == ["Своя"]


async def test_search_does_not_find_another_workspace(titles, session_factory):
    await put_other_workspace(session_factory)
    await put(
        session_factory, vacancy_row(title="Golang", workspace_id=OTHER_WORKSPACE_ID)
    )

    assert await titles(search="Golang") == []


async def test_filter_options_come_only_from_the_active_workspace(session, session_factory):
    channel = channel_row(username="foreign")
    company = company_row(name="Чужая")
    await put_other_workspace(session_factory)
    await put(session_factory, channel, company)
    await put(
        session_factory,
        vacancy_row(
            source_channel_id=channel.id, company_id=company.id, company_name="Чужая",
            workspace_id=OTHER_WORKSPACE_ID,
        ),
    )

    assert await list_vacancy_filter_options(session) == {"channels": [], "companies": []}


async def test_kpi_and_funnel_count_only_the_active_workspace(session, session_factory):
    applied = {"status": VacancyStatus.APPLIED, "created_at": days_ago(1)}
    mine = vacancy_row(**applied)
    foreign = vacancy_row(**applied, workspace_id=OTHER_WORKSPACE_ID)
    await put_other_workspace(session_factory)
    await put(session_factory, mine, foreign)
    await put(
        session_factory,
        status_history_row(mine.id, changed_at=days_ago(1)),
        status_history_row(foreign.id, changed_at=days_ago(1)),
    )

    kpi = await get_stats_kpi(session, period="week")
    breakdown = await get_stats_status_breakdown(session, period="week")

    totals = ("total", "applied_total", "total_period", "applied_period")
    assert [kpi[name] for name in totals] == [1, 1, 1, 1]
    assert breakdown["counts"][VacancyStatus.APPLIED.value] == 1


async def test_response_speed_counts_only_the_active_workspace(
    session, session_factory, applied
):
    await put_other_workspace(session_factory)
    await applied(at(0))
    await applied(at(0), workspace_id=OTHER_WORKSPACE_ID)

    assert (await get_stats_hr_responses(session, period="all"))["applied_count"] == 1


async def test_trash_counts_only_the_active_workspace(session, session_factory):
    channel = channel_row()
    await put_other_workspace(session_factory)
    await put(session_factory, channel)
    await put(
        session_factory,
        trash_event_row(source_channel_id=channel.id, source_msg_id=1),
        trash_event_row(
            source_channel_id=channel.id, source_msg_id=2, workspace_id=OTHER_WORKSPACE_ID
        ),
    )

    row = (await rows_by_channel(session, period="all"))[channel.id]

    assert row["trash"] == 1


async def test_the_source_table_counts_only_the_active_workspace(session, session_factory):
    channel = channel_row()
    await put_other_workspace(session_factory)
    await put(session_factory, channel)
    mine = vacancy_row(source_channel_id=channel.id, status=VacancyStatus.APPLIED)
    foreign = vacancy_row(
        source_channel_id=channel.id, status=VacancyStatus.APPLIED,
        workspace_id=OTHER_WORKSPACE_ID,
    )
    await put(session_factory, mine, foreign)
    await put(session_factory, status_history_row(mine.id), status_history_row(foreign.id))

    got = await get_stats_channels_pipeline(session, period="all")

    (row,) = got["channels"]
    assert (row["total"], row["sent"]) == (1, 1)


async def test_the_source_card_counts_only_the_active_workspace(session, session_factory):
    channel = channel_row()
    await put_other_workspace(session_factory)
    await put(session_factory, channel)
    # По три в профиле: одна вакансия за 30 дней округляется в темпе до нуля.
    recent = {"source_channel_id": channel.id, "created_at": days_ago(1)}
    await put(
        session_factory,
        *[vacancy_row(**recent) for _ in range(3)],
        *[vacancy_row(**recent, workspace_id=OTHER_WORKSPACE_ID) for _ in range(3)],
    )

    stats = (await get_channel_detail(session, channel.id)).stats

    assert (stats.total, stats.vacancies_per_day) == (3, 0.1)


async def test_list_counters_count_only_the_active_workspace(session, session_factory):
    hr = hr_row()
    company = company_row()
    channel = channel_row()
    site = aggregator_row()
    await put_other_workspace(session_factory)
    await put(session_factory, hr, company, channel, site)
    shared = {"hr_id": hr.id, "company_id": company.id}
    await put(
        session_factory,
        vacancy_row(source_channel_id=channel.id, **shared),
        vacancy_row(source_channel_id=channel.id, workspace_id=OTHER_WORKSPACE_ID, **shared),
        vacancy_row(source_aggregator_id=site.id),
        vacancy_row(source_aggregator_id=site.id, workspace_id=OTHER_WORKSPACE_ID),
    )

    (hr_counted,), _ = await list_hr_with_counts(session)
    (company_counted,), _ = await list_companies_with_counts(session)
    (channel_counted,) = await list_telegram_channels(session)
    site_counts = {row.id: cnt for row, cnt, _ in await list_aggregators_with_counts(session)}

    assert hr_counted.vacancy_count == 1
    assert company_counted.vacancy_count == 1
    assert channel_counted.vacancy_count == 1
    assert site_counts[site.id] == 1


async def test_a_company_card_keeps_hrs_of_other_workspaces(session, session_factory):
    company = company_row()
    here = hr_row(name="Анна", telegram_username="anna")
    there = hr_row(name="Борис", telegram_username="boris")
    await put_other_workspace(session_factory)
    await put(session_factory, company, here, there)
    await put(
        session_factory,
        vacancy_row(company_id=company.id, hr_id=here.id),
        vacancy_row(company_id=company.id, hr_id=there.id, workspace_id=OTHER_WORKSPACE_ID),
    )

    got = await list_hrs_for_company(session, company.id)

    assert [(hr.name, cnt) for hr, cnt in got] == [("Анна", 1), ("Борис", 0)]


async def test_card_lists_show_foreign_vacancies_last(session, session_factory):
    hr = hr_row()
    company = company_row()
    channel = channel_row()
    await put_other_workspace(session_factory)
    await put(session_factory, hr, company, channel)
    linked = {"hr_id": hr.id, "company_id": company.id, "source_channel_id": channel.id}
    await put(
        session_factory,
        vacancy_row(title="Своя", created_at=at(0), **linked),
        vacancy_row(
            title="Чужая", created_at=at(60), workspace_id=OTHER_WORKSPACE_ID, **linked
        ),
    )

    from_channel, _ = await list_vacancies_from(session, CHANNEL_KIND, channel.id)

    for rows in (
        await list_vacancies_for_hr(session, hr.id),
        await list_vacancies_for_company(session, company.id),
        from_channel,
    ):
        assert [v.title for v in rows] == ["Своя", "Чужая"]
