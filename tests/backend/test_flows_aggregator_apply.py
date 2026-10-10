"""Фаза 2: отклик способ за способом, пока один не удался или способы не кончились."""

import asyncio
import threading
import time

import pytest

from backend.agent.sessions import LimitExhausted

from backend.flows.aggregator_apply import ApplyOrder, apply_phase, apply_vacancy
from backend.flows.aggregator_round import RoundState
from backend.models import Application, ContactAddedBy, Vacancy, VacancyEvent, VacancyStatus
from backend.repository.app_settings import CV_PATH_KEY
from backend.repository.mail_account import MailSettings, save_mail_account
from tests.dbio import all_rows, put
from tests.factories import vacancy_row
from tests.factories_aggregators import aggregator_row, vacancy_contact_row
from tests.fakes.agent import LimitHit, scripted_kit
from tests.waiting import wait_until

PAGE = "https://site.test/vacancy/1"
FORM = "https://company.test/apply"


@pytest.fixture
def board(session_factory):
    """Залогиненный агрегатор и вакансия с него: кнопка агрегатора, затем форма из контактов."""

    async def make(**vacancy):
        site = aggregator_row(host="site.test", is_logged_in=True, is_active=True)
        await put(session_factory, site)
        row = vacancy_row(**{"status": VacancyStatus.NEW, "source_aggregator_id": site.id,
                             "source_key": "vacancy/1", "source_url": PAGE, **vacancy})
        await put(session_factory, row)
        await put(session_factory, vacancy_contact_row(row.id, FORM))
        return site, row

    return make


@pytest.fixture
def applying(make_pipeline):
    """Отклик по сценарию; ответ — итог, водитель и состояние обхода."""

    async def run(vacancy_id, steps, round_=None):
        kit = scripted_kit(await make_pipeline(), steps)
        driver = kit.run_session
        round_ = round_ or RoundState(set(), web_search_id=0)
        return await apply_vacancy(kit, round_, ApplyOrder(vacancy_id, False, None)), driver, round_

    return run


def _record(target):
    async def step(tools):
        await tools["record_application"](via="aggregator" if target == PAGE else "form", target=target)
    return step


def _fail(reason):
    async def step(tools):
        await tools["report_failure"](reason=reason)
    return step


def _finish(result):
    async def step(tools):
        await tools["finish"](result=result)
    return step


async def _events(session_factory, kind):
    return [e.payload for e in await all_rows(session_factory, VacancyEvent) if e.kind == kind]


async def test_the_first_way_that_works_ends_the_vacancy(board, applying, session_factory):
    _, vacancy = await board()

    outcome, driver, _ = await applying(vacancy.id, [_record(PAGE)])

    assert outcome == "applied" and len(driver.plans) == 1
    (stored,) = await all_rows(session_factory, Vacancy)
    assert stored.status is VacancyStatus.APPLIED


async def test_the_applier_is_told_how_to_call_a_person(board, applying):
    """Откликатель зовёт человека на капчу и слетевший вход — правило о том в его наставлении."""
    _, vacancy = await board()

    _, driver, _ = await applying(vacancy.id, [_record(PAGE)])

    (plan,) = driver.plans
    # Подстрока самого правила о зове человека: слово `need_human` называет и
    # промпт роли, и по нему пропажу правила не заметить.
    assert 'need_human с kind="captcha"' in plan.system_prompt


async def test_a_failed_way_hands_over_to_the_next_and_all_failures_are_told(
    board, applying, session_factory
):
    _, vacancy = await board()

    outcome, driver, _ = await applying(vacancy.id, [_fail("капча"), _fail("форма сломана")])

    assert outcome == "exhausted" and len(driver.plans) == 2
    (stored,) = await all_rows(session_factory, Vacancy)
    assert stored.status is VacancyStatus.NEW
    assert await _events(session_factory, "apply_failed") == [
        {"method": "aggregator", "reason": "капча"}, {"method": "form", "reason": "форма сломана"},
    ]


async def test_a_closed_vacancy_is_not_tried_another_way(board, applying, session_factory):
    _, vacancy = await board()

    outcome, driver, _ = await applying(vacancy.id, [_finish("vacancy_closed")])

    assert outcome == "closed" and len(driver.plans) == 1
    assert len(await _events(session_factory, "vacancy_closed")) == 1


async def test_a_closed_platform_drops_its_button_for_the_rest_of_the_round(
    board, applying, session_factory
):
    site, vacancy = await board()
    second = vacancy_row(status=VacancyStatus.NEW, source_aggregator_id=site.id,
                         source_key="vacancy/2", source_url="https://site.test/vacancy/2")
    await put(session_factory, second)

    _, _, round_ = await applying(vacancy.id, [_finish("platform_closed"), _fail("нет")])
    _, driver, _ = await applying(second.id, [], round_=round_)

    assert round_.closed_aggregators == {site.id}
    assert driver.plans == []


async def test_a_session_without_an_outcome_is_a_failure(board, applying, session_factory):
    _, vacancy = await board()

    async def silent(tools):
        return None

    await applying(vacancy.id, [silent, silent])

    reasons = [e["reason"] for e in await _events(session_factory, "apply_failed")]
    assert reasons == ["агент закончил без итога", "агент закончил без итога"]


async def test_the_phase_skips_vacancies_that_left_new(board, make_pipeline, session_factory):
    _, vacancy = await board(status=VacancyStatus.NOT_FIT)
    kit = scripted_kit(await make_pipeline(), [])
    driver = kit.run_session

    await apply_phase(kit, RoundState(set(), web_search_id=0), [vacancy.id])

    assert driver.plans == []


async def test_the_phase_skips_vacancies_left_unparsed(board, make_pipeline, session_factory):
    """Не разобранная — без балла и приговора: откликаться на неё рано."""
    _, vacancy = await board(is_parsed=False)
    kit = scripted_kit(await make_pipeline(), [])
    driver = kit.run_session

    await apply_phase(kit, RoundState(set(), web_search_id=0), [vacancy.id])

    assert driver.plans == []


async def test_an_exhausted_subscription_stops_the_round_not_just_the_way(board, applying):
    """Следующий способ упёрся бы в тот же лимит."""
    _, vacancy = await board()

    async def limit(tools):
        raise LimitHit

    with pytest.raises(LimitExhausted):
        await applying(vacancy.id, [limit])


async def test_a_crashed_way_is_a_failure_and_the_next_way_is_tried(board, applying, session_factory):
    _, vacancy = await board()

    async def crash(tools):
        raise RuntimeError("сломалось")

    outcome, driver, _ = await applying(vacancy.id, [crash, _record(FORM)])

    assert outcome == "applied" and len(driver.plans) == 2
    assert await _events(session_factory, "apply_failed") == [
        {"method": "aggregator", "reason": "сбой приложения"}
    ]


async def test_the_email_way_needs_no_browser(make_pipeline, session, session_factory):
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)
    await put(session_factory, vacancy_contact_row(vacancy.id, "hr@company.test",
                                                   added_by=ContactAddedBy.PARSE))
    async with session.begin():
        await save_mail_account(session, MailSettings("me@mail.test", "secret", "smtp.mail.test", 465))

    async def fail(tools):
        await tools["report_failure"](reason="нет")

    kit = scripted_kit(await make_pipeline(), [fail])
    await apply_vacancy(kit, RoundState(set(), web_search_id=0),
                        ApplyOrder(vacancy.id, False, None))

    (plan,) = kit.run_session.plans
    assert not [t.__name__ for t in plan.tools if t.__name__.startswith("browser_")]
    assert kit.browser.calls == []


async def test_a_simulated_application_is_told_not_to_send_and_is_marked(
    board, make_pipeline, session_factory
):
    """Последнюю кнопку формы код не знает: «не отправлять» агенту говорит задание,
    а отклик записывается с пометкой симуляции."""
    _, vacancy = await board()

    async def record(tools):
        await tools["record_application"](via="aggregator", target=PAGE)

    pipeline = await make_pipeline()
    await pipeline.rs.set_app("send_locked", "true")
    kit = scripted_kit(pipeline, [record])

    await apply_vacancy(kit, RoundState(set(), web_search_id=0),
                        ApplyOrder(vacancy.id, False, None))

    (plan,) = kit.run_session.plans
    assert "Режим симуляции" in plan.task
    assert kit.browser.sending is False
    (event,) = await _events(session_factory, "applied_elsewhere")
    assert event["simulated"] is True


@pytest.fixture
async def slow_letter(make_pipeline, session, session_factory, tmp_path, monkeypatch):
    """Вакансия с двумя адресами; сессия уходит, пока сервер почты принимает первое письмо.
    Ответ — набор и вакансия."""
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)
    await put(session_factory,
              vacancy_contact_row(vacancy.id, "hr@company.test", added_by=ContactAddedBy.PARSE),
              vacancy_contact_row(vacancy.id, "boss@company.test", added_by=ContactAddedBy.PARSE))
    async with session.begin():
        await save_mail_account(session, MailSettings("me@mail.test", "secret", "smtp.mail.test", 465))
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF")
    sending = threading.Event()

    def slow_server(account, mail):
        sending.set()
        time.sleep(0.2)

    monkeypatch.setattr("adapters.smtp_mail.send_mail", slow_server)

    async def leave_while_sending(tools):
        asyncio.get_running_loop().create_task(
            tools["send_email"](address="hr@company.test", subject="Отклик", body="Текст"))
        await wait_until(sending.is_set)

    pipeline = await make_pipeline()
    await pipeline.rs.set_app(CV_PATH_KEY, str(cv))
    return scripted_kit(pipeline, [leave_while_sending, _fail("второй способ")]), vacancy


async def test_a_letter_still_on_its_way_holds_the_next_way(slow_letter):
    """Сессия кончилась, пока сервер почты принимал письмо: письмо дойдёт и запишется,
    а второй способ не пробуется — иначе второе письмо ушло бы тому же работодателю."""
    kit, vacancy = slow_letter

    outcome = await apply_vacancy(kit, RoundState(set(), web_search_id=0),
                                  ApplyOrder(vacancy.id, False, None))

    assert outcome == "applied" and len(kit.run_session.plans) == 1


async def test_a_stop_while_the_letter_is_on_its_way_does_not_cut_it_off(
    slow_letter, session_factory
):
    """Обход остановили, пока он ждал письмо: письмо всё равно доходит и записывается."""
    kit, vacancy = slow_letter
    applying = asyncio.create_task(apply_vacancy(kit, RoundState(set(), web_search_id=0),
                                                 ApplyOrder(vacancy.id, False, None)))
    await wait_until(lambda: kit.run_session.plans)
    await asyncio.sleep(0.05)

    applying.cancel()
    with pytest.raises(asyncio.CancelledError):
        await applying
    await asyncio.sleep(0.4)

    assert len(await all_rows(session_factory, Application)) == 1


async def test_a_real_application_opens_the_browser_able_to_send(board, make_pipeline):
    _, vacancy = await board()
    kit = scripted_kit(await make_pipeline(), [_record(PAGE)])

    await apply_vacancy(kit, RoundState(set(), web_search_id=0), ApplyOrder(vacancy.id, False, None))

    assert kit.browser.sending is True
