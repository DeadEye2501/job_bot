"""Инструкции сайтов: задание работы на сайте несёт устройство этого сайта."""

from types import SimpleNamespace

import pytest

from backend.agent.prompts import site_guides
from backend.agent.prompts.applier import applier_task
from backend.agent.prompts.fill import fill_task
from backend.agent.prompts.login import login_task
from backend.agent.prompts.scan import scan_task
from backend.domain.apply_order import Way
from backend.models import ApplicationVia
from tests.fakes.agent import TODAY

GUIDE = "Раздел заказов — в меню слева."


@pytest.fixture(autouse=True)
def _guide(monkeypatch):
    monkeypatch.setitem(site_guides.SITE_GUIDES, "board.test", GUIDE)


def _apply(target: str) -> str:
    job = SimpleNamespace(way=Way(ApplicationVia.AGGREGATOR.value, target, None), simulated=False,
                          letter_writer="app", confirming=False, resume=None, language="Русский")
    return applier_task(job, "Текст вакансии", "Анкета", TODAY)


TASKS = {
    "login": login_task,
    "scan": scan_task,
    "fill": lambda host: fill_task(host, None, "Русский"),
    "apply": lambda host: _apply(f"https://{host}/vacancy/1"),
}


@pytest.mark.parametrize("task", TASKS.values(), ids=TASKS.keys())
def test_a_task_on_a_site_with_a_guide_carries_it(task):
    assert GUIDE in task("board.test")


@pytest.mark.parametrize("task", TASKS.values(), ids=TASKS.keys())
def test_a_subdomain_finds_the_guide_of_its_site(task):
    assert GUIDE in task("my.board.test")


@pytest.mark.parametrize("task", TASKS.values(), ids=TASKS.keys())
def test_a_task_on_a_site_without_a_guide_has_no_guide_block(task):
    built = task("other.test")
    assert GUIDE not in built and "Устройство этого сайта" not in built


def test_a_look_alike_host_is_not_the_site():
    """Хост, лишь кончающийся на имя сайта, — другой сайт."""
    assert GUIDE not in login_task("notboard.test")


def test_an_application_off_the_site_gets_no_guide():
    assert GUIDE not in _apply("https://employer.test/jobs/board.test")
