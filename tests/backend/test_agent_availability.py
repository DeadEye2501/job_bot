"""Агенту нужны водитель и браузер; без них агрегаторы заперты с подсказкой."""

from backend.agent.availability import NO_BROWSER, NO_DRIVER, agent_refusal
from backend.provider_config import CLAUDE_CODE_ADDRESS, LlmProviderConfig
from tests.fakes.browser import CHROME


def test_claude_code_and_a_browser_unlock_the_agent():
    assert agent_refusal(LlmProviderConfig(CLAUDE_CODE_ADDRESS, "", "opus"), CHROME) is None


def test_a_chat_provider_that_cannot_drive_locks_it():
    assert agent_refusal(LlmProviderConfig("http://localhost:1234", "", "qwen"), CHROME) == NO_DRIVER


def test_no_chat_provider_locks_it_too():
    assert agent_refusal(None, CHROME) == NO_DRIVER


def test_no_browser_locks_it():
    assert agent_refusal(LlmProviderConfig(CLAUDE_CODE_ADDRESS, "", "opus"), None) == NO_BROWSER
