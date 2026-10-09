"""Сборка промптов агента: что код подставляет и чего в них быть не может."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.agent.prompts.applier import APPLIER_PROMPT, applier_task
from backend.agent.prompts.frame import system_prompt
from backend.agent.prompts.login import LOGIN_PROMPT, login_task
from backend.agent.prompts.seeker import (
    SEEKER_PROMPT, WEB_SEEKER_PROMPT, seeker_task, web_seeker_task,
)
from backend.llm.rules import FACT_KINDS, GENDER_RULE, LATIN_NAME_RULE, TONE_RULE
from backend.models import ApplicationVia
from backend.runtime_settings import LETTER_WRITERS
from tests.factories import person_fields
from tests.fakes.agent import TODAY

ROLES = [LOGIN_PROMPT, SEEKER_PROMPT, WEB_SEEKER_PROMPT]
SHARED_RULES = [TONE_RULE, GENDER_RULE, LATIN_NAME_RULE, FACT_KINDS]


@pytest.mark.parametrize("role", ROLES)
def test_every_role_works_inside_the_common_frame(role):
    built = system_prompt(role)
    assert built.endswith(role)
    assert "need_human" in built and "finish" in built


@pytest.mark.parametrize("rule", SHARED_RULES)
@pytest.mark.parametrize("role", ROLES)
def test_every_role_hears_each_voice_rule_once(role, rule):
    """Правило голоса приходит из общего объявления и ровно один раз."""
    assert system_prompt(role).count(rule) == 1


@pytest.mark.parametrize("role", ROLES)
def test_no_slot_is_left_unfilled(role):
    assert "{" not in system_prompt(role)


@pytest.mark.parametrize("role", ROLES)
def test_a_prompt_carries_nothing_about_the_person(role):
    """Всё о человеке приходит из анкеты инструментом, а не из текста промпта."""
    built = system_prompt(role)
    for value in person_fields().values():
        assert value not in built


def test_the_seeker_task_names_its_source_and_bounds():
    task = seeker_task("site.test", datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc), 20, TODAY)
    assert "site.test" in task and "20" in task and "2026-10-09" in task
    assert "2026-10-01 09:30" in task


def test_a_first_run_says_so():
    assert "первый обход" in seeker_task("site.test", None, 20, TODAY)


def test_the_web_seeker_is_told_which_sites_to_leave_alone():
    task = web_seeker_task(["board-a.test", "board-b.test"], None, 5, TODAY)
    assert "board-a.test" in task and "board-b.test" in task


def test_the_login_check_knows_the_site():
    assert "site.test" in login_task("site.test")


def _task(vacancy_text="Текст вакансии", profile_text="Анкета", **job) -> str:
    fields = dict(
        method=ApplicationVia.FORM.value, target="https://site.test/form",
        simulated=False, letter_writer="app",
    )
    fields.update(job)
    return applier_task(SimpleNamespace(**fields), vacancy_text, profile_text, TODAY)


def test_the_task_says_who_writes_the_letter():
    assert "Письмо пишешь ты" in _task(letter_writer="agent")
    assert "Письмо пишет: приложение" in _task(letter_writer="app")


@pytest.mark.parametrize("writer", LETTER_WRITERS)
def test_every_letter_writer_is_spelled_out(writer):
    """Новое значение набора без своей строки падает здесь, а не в прогоне."""
    assert "Письмо пиш" in _task(letter_writer=writer)


_METHOD_NAMES = {
    ApplicationVia.AGGREGATOR: "кнопка отклика на сайте агрегатора",
    ApplicationVia.FORM: "форма работодателя",
    ApplicationVia.EMAIL: "письмо",
}


@pytest.mark.parametrize("via", list(ApplicationVia))
def test_every_method_has_its_name_and_its_simulation(via):
    """Новый способ без своей подписи в этой таблице падает здесь KeyError-ом."""
    name = _METHOD_NAMES[via]
    task = _task(method=via.value, simulated=True)
    assert f"Способ отклика: {name}\n" in task and "Режим симуляции" in task


def test_the_applier_prompt_is_clean_too():
    built = system_prompt(APPLIER_PROMPT)
    assert "{" not in built
    for value in person_fields().values():
        assert value not in built


@pytest.mark.parametrize("rule", SHARED_RULES)
def test_the_applier_hears_each_voice_rule_once(rule):
    """Рамка, правила письма и скрининг вместе не повторяют правило голоса."""
    assert system_prompt(APPLIER_PROMPT).count(rule) == 1


def test_the_applier_task_carries_its_vacancy_method_and_profile():
    task = _task()
    assert "Текст вакансии" in task and "https://site.test/form" in task
    assert "Анкета" in task and "2026-10-09" in task


def test_simulation_is_spelled_out_in_the_task():
    """Под симуляцией агент проходит форму, но последнюю кнопку не нажимает."""
    assert "НЕ нажимай" in _task(simulated=True)
    assert "НЕ нажимай" not in _task(simulated=False)


def test_a_simulated_letter_is_not_told_to_record_by_hand():
    """У почты инструмента record_application нет: запись делает send_email."""
    assert "record_application" not in _task(method=ApplicationVia.EMAIL.value, simulated=True)
