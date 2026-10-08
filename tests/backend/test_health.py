"""Следствия вопроса «живо ли то, на чём держится работа».

Ответ на него рисует лампочка в шапке окна, и цена ошибки здесь несимметрична:
погасшая зря лампочка отправляет человека чинить работающее, а горящая зря —
оставляет его в уверенности, что всё в порядке, пока бот молчит.
"""

import os

import httpx

from adapters import lm_studio
from backend.health import database_alive, model_alive, telegram_alive
from backend.provider_config import LlmProviderConfig
from tests.fakes.gguf import model_file


class Stopped:
    """Фабрика сессий, у которой движок уже закрыт."""

    def __call__(self):
        raise RuntimeError("Engine is disposed")


class Bot:
    def __init__(self, connected: bool) -> None:
        self.is_connected = connected


async def test_a_closed_engine_darkens_the_lamp(session_factory):
    """Закрытый движок гасит лампочку базы, а не уносит весь ответ.

    Движок закрывают на сносе данных, и тик часов после этого приходит на
    пустое место. Выброс отсюда унёс бы ответ целиком — окно молча выбросило
    бы его, и человек смотрел бы на застывшую зелёную лампочку.
    """
    assert await database_alive(session_factory) is True
    assert await database_alive(Stopped()) is False


def test_a_bot_that_is_not_there_is_not_healthy():
    """Бота нет — Telegram не здоров, а не «неизвестно».

    До входа в учётную запись бота не существует вовсе. Считай мост это
    неизвестностью — лампочка горела бы зелёной на пустом месте.
    """
    assert telegram_alive(None) is False
    assert telegram_alive(Bot(connected=False)) is False
    assert telegram_alive(Bot(connected=True)) is True


async def test_a_provider_address_that_will_not_parse_darkens_the_lamp():
    """Негодный адрес поставщика гасит лампочку, а не уносит весь ответ.

    Клиент собирался до перехвата, и «http://localhost:12ab» — опечатка в
    порте, которую человек делает легко, — ронял сборку броском. Тот проходил
    насквозь до ответа окну: вместо погашенных лампочек человек видел красную
    плашку с английской поломкой, а вместе с ответом терялись счёт
    непрочитанного и режим — их спрашивают тем же зовом, и второй попытки нет.
    """
    broken = LlmProviderConfig(base_url="http://localhost:12ab", api_key="", model="qwen")

    assert await model_alive(broken, "chat") is False


def _provider(monkeypatch, *, listed: list[str]) -> list[str]:
    """Подставной поставщик: перечень отдаёт, на всё прочее жалуется.

    Так выглядит модель, чем-то занятая: числится в перечне, а на обращение
    отвечает отказом. Отдаёт список путей, которыми её потревожили сверх
    перечня, — пустой он и есть главное следствие.
    """
    knocked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": one} for one in listed]})
        knocked.append(request.url.path)
        return httpx.Response(400, json={"error": "the model is busy"})

    monkeypatch.setattr(
        lm_studio,
        "make_client",
        lambda _cfg: httpx.AsyncClient(
            base_url="http://provider.test", transport=httpx.MockTransport(answer)
        ),
    )
    return knocked


async def test_the_lamp_answers_by_the_list_alone(monkeypatch):
    """Лампочка отвечает вхождением имени в перечень — и ничем больше.

    Обе половины здесь вместе нарочно. Молчащая модель лампочку не гасит:
    настоящее обращение пошло бы к той же модели, которой в эту минуту
    работает бот, а окно на погасшую лампочку переводит бота в Off посреди
    обхода. Но и «всегда зелёная» не годится: имя модели правят руками, и
    опечатка в нём означает, что не разберётся ни одна вакансия.
    """
    cfg = LlmProviderConfig(base_url="http://provider.test", api_key="", model="qwen")

    knocked = _provider(monkeypatch, listed=["qwen"])
    assert await model_alive(cfg, "chat") is True
    assert knocked == []

    _provider(monkeypatch, listed=["llama"])
    assert await model_alive(cfg, "chat") is False


async def test_a_model_file_lamp_follows_the_file_on_disk(tmp_path):
    """Лампочка эмбеддингов из файла горит, пока файл лежит на диске.

    Убранный или перенесённый файл гасит её, а с ней запирается тумблер: бот
    не уходит в обход, который не сможет посчитать ни одного поста.
    """
    path = model_file(tmp_path)

    assert await model_alive(LlmProviderConfig("", "", path), "embed") is True
    os.remove(path)
    assert await model_alive(LlmProviderConfig("", "", path), "embed") is False
