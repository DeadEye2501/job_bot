"""Следствия мастера первого запуска: с какого шага он продолжает и чем кончается.

Предмет — сам порядок первого запуска. Шаги, которые мастер делает вместе с
основным окном — вход в Telegram, проверка модели, выбор резюме, — лежат со
своими предметами: тела у них общие, и проверять их дважды незачем.
"""

import json

import pytest

from backend.crypto import encrypt_str
from backend.models import LlmConfigKind
from backend.runtime_settings import RuntimeSettings
from client.bridge import WizardApi
from tests.dbio import put
from tests.factories import llm_config_row, tg_account_row


class Handoff:
    """Переход в основное окно: то, что мастер зовёт напоследок."""

    def __init__(self) -> None:
        self.entered = 0

    def __call__(self) -> None:
        self.entered += 1


@pytest.fixture
def handoff() -> Handoff:
    return Handoff()


@pytest.fixture
async def wizard_with_handoff(runtime_settings, session_factory, runner, handoff):
    """Мастер, которому есть куда передать управление."""
    api = WizardApi(
        runtime_settings, session_factory, runner, on_enter_main=handoff
    )
    yield api
    await runner.drain()


async def test_an_empty_setup_has_no_steps_behind_it(wizard_api):
    """На пустой установке пройденных шагов нет ни одного.

    По этому списку мастер решает, с какого шага открыться. Соври он про
    пройденное — человек попал бы сразу на последний шаг, не введя ни
    учётной записи, ни модели.
    """
    answer = json.loads(wizard_api.initial_state())

    assert answer["completed"] == []
    assert answer["wizard_completed"] is False


async def test_credentials_without_a_session_do_not_count_as_a_step(
    wizard_api, session_factory
):
    """Введённые учётные данные без сохранённой сессии шагом не считаются.

    Данные вводят на первом шаге, а сессия появляется только после кода
    подтверждения. Засчитай мастер шаг раньше — человек ушёл бы дальше, а
    бот при запуске не подключился бы, и причина осталась бы в прошлом шаге.

    Хэш записываем настоящим: без него запись учётной записи не читается
    вовсе, и шаг не засчитался бы по другой причине — тест был бы зелен, не
    проверив ничего.
    """
    await put(
        session_factory,
        tg_account_row(
            api_hash_encrypted=encrypt_str("ш"), session_blob_encrypted=None
        ),
    )
    await wizard_api._rs.reload()

    answer = json.loads(wizard_api.initial_state())

    assert answer["completed"] == []
    assert answer["tg"]["api_hash"] == "ш"


async def test_a_saved_model_counts_as_a_step(wizard_api, session_factory):
    """Сохранённая чат-модель засчитывается пройденным шагом.

    Мастер продолжают в другой день и с другого запуска; шаги, сделанные
    вчера, переспрашивать незачем.
    """
    await put(session_factory, llm_config_row(LlmConfigKind.CHAT))
    await wizard_api._rs.reload()

    answer = json.loads(wizard_api.initial_state())

    assert 2 in answer["completed"]


async def test_finishing_does_not_yet_mark_the_setup_as_done(wizard_api, watch):
    """Нажатие «готово» само по себе установку завершённой не помечает.

    Отметку ставят только при настоящем переходе в основное окно: упади
    приложение между этими двумя мигами, следующий запуск пропустил бы
    последний экран мастера, так и не показав его.
    """
    caught = watch(wizard_api.finish_done)

    wizard_api.finish()
    assert (await caught.next())["ok"] is True

    assert json.loads(wizard_api.initial_state())["wizard_completed"] is False


async def test_entering_the_main_window_marks_the_setup_as_done(
    wizard_with_handoff, handoff, session_factory
):
    """Переход в основное окно и отмечает установку, и передаёт управление.

    Отметка решает, что покажет следующий запуск, а передача — что человек
    увидит сейчас. Пропади первая, мастер открывался бы каждый раз заново;
    пропади вторая — человек остался бы на последнем экране мастера навсегда.
    """
    wizard = wizard_with_handoff

    wizard.enter_main_app()
    for started in list(wizard._runner.tasks):
        await started

    assert handoff.entered == 1
    assert (await RuntimeSettings.load(session_factory)).wizard_completed is True


