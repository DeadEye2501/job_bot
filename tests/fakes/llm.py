"""Подделка провайдера LLM: настоящий клиент поверх подставного транспорта.

Подменена только доставка. Клиент настоящий, поэтому тесты проверяют и
заголовок с ключом, и разбор ответа, и обработку кода состояния — то есть всё,
что на самом деле делает боевой код.

Незарегистрированный путь возвращает 599 с его именем в теле: забытый ответ
виден сразу и называет себя, а не превращается в загадочное падение разбора.

Значением маршрута может быть исключение — тогда подделка его бросает. Это
нужно веткам `except httpx.RequestError`: «сеть отвалилась» кодом состояния не
изображается, только исключением.

Так изображается ТОЛЬКО отказ доставки (обрыв связи, таймаут и другие
httpx.RequestError). Не кладите сюда исключением httpx.HTTPStatusError:
боевой код получает его из `raise_for_status()` уже после того, как ответ
получен, а не из самой доставки. Статусный отказ (4xx/5xx) изображайте
ответом с нужным кодом — `httpx.Response(500, ...)`, — а не исключением.

Значением маршрута может быть и список: тогда обращения к одному пути получают
ответы по очереди. Это нужно там, где боевой код ходит по одному пути дважды за
вызов и ждёт разного — сперва за письмом, потом за проверкой его фактов: письмо
отклоняется, если содержит фигурную скобку, а вердикт проверки обязан быть
объектом JSON, и одной строкой их не обслужить. Список короче числа обращений —
ошибка теста, и подделка говорит об этом прямо, а не отдаёт последний ответ по
кругу.
"""

import json

import httpx
import pytest


# Пары «метод, путь», по которым подделка раскладывает заготовленные ответы.
# Держатся здесь, а не в каждом файле проверок: путь один на весь проект, и
# десять его копий разошлись бы при первой же смене адреса у провайдера.
CHAT = ("POST", "/v1/chat/completions")
EMBEDDINGS = ("POST", "/v1/embeddings")
MODELS = ("GET", "/v1/models")


def _troubles() -> list[tuple[str, object, str]]:
    """Четыре беды провайдера: имя случая, заготовленное для подделки и метка,
    которой боевой код называет эту беду в журнале и в причине отказа.

    Отказ кодом состояния, обрыв связи, ответ чужой формы и ответ без
    содержимого ждёт каждое обращение к модели, поэтому перечень один на все
    проверки: выписанный по месту, он расходился бы, и ветка, забытая в одном
    файле, выглядела бы проверенной.

    Собирается заново на каждый зов: подделка проставляет обращение в ошибку
    связи, а один объект достался бы всем файлам сразу.
    """
    return [
        ("отказ провайдера", httpx.Response(500, text="упал"), "llm_http_error"),
        ("обрыв связи", httpx.ConnectError("сеть отвалилась"), "llm_request_error"),
        (
            "чужая форма",
            httpx.Response(200, json={"нет": "выборов"}),
            "malformed_response",
        ),
        ("пустое содержимое", chat_response(None), "empty_content"),
    ]


def provider_trouble(*extra):
    """Беды провайдера, на которых обращение к модели обязано отдать пустое.

    `extra` — беды, свойственные одному предмету: у проверки фактов сверх
    общих есть ещё четыре формы неразбираемого вердикта.
    """
    return [pytest.param(prepared, id=name) for name, prepared, _ in _troubles()] + list(
        extra
    )


def provider_trouble_named(*extra):
    """То же, но парой «беда, метка»: разбор сведения компаний не просто
    отказывает, а называет причину, и сверяется именно она.
    """
    return [
        pytest.param(prepared, mark, id=name) for name, prepared, mark in _troubles()
    ] + list(extra)


def _picker(routes: dict):
    """Выдаёт заготовленное для пары «метод, путь», списки — по очереди."""
    queues = {
        key: list(value) for key, value in routes.items() if isinstance(value, list)
    }

    def pick(key: tuple[str, str]):
        if key not in queues:
            return routes.get(key)
        if not queues[key]:
            return httpx.Response(
                599, text=f"ответов для {key[0]} {key[1]} меньше, чем обращений"
            )
        return queues[key].pop(0)

    return pick


def provider(
    routes: dict[tuple[str, str], httpx.Response | BaseException | list],
    *,
    api_key: str = "",
) -> httpx.AsyncClient:
    """Клиент к поддельному провайдеру. Ключ маршрута — пара «метод, путь».

    Полученные запросы копятся в `client.sent` по порядку: без этого не
    проверить, что именно ушло на ту сторону — например, что длинный текст
    урезан перед отправкой.
    """
    sent: list[httpx.Request] = []
    pick = _picker(routes)

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        key = (request.method, request.url.path)
        prepared = pick(key)
        if prepared is None:
            return httpx.Response(
                599, text=f"тест не задал ответ для {key[0]} {key[1]}"
            )
        if isinstance(prepared, BaseException):
            # У ошибок httpx запрос — обязательное поле, и без него обращение
            # к нему поднимает RuntimeError вместо самой ошибки.
            if isinstance(prepared, httpx.RequestError):
                prepared.request = request
            raise prepared
        return prepared

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    client = httpx.AsyncClient(
        base_url="http://provider.test",
        headers=headers,
        transport=httpx.MockTransport(handle),
    )
    client.sent = sent
    return client


def models_response(*ids: str) -> httpx.Response:
    """Ответ `/v1/models` в форме, совместимой с OpenAI."""
    return httpx.Response(200, json={"data": [{"id": one} for one in ids]})


def parsed_vacancy_answer(**fields) -> dict:
    """Разобранная вакансия в ответе модели: одно название, остальное по месту.

    Название — единственное поле, без которого разбор отвергает ответ вовсе,
    поэтому минимум состоит из него. Проверки, которым нужно ещё что-то,
    дописывают своё доводами, а не собирают ответ заново.
    """
    return {"title": "Python-разработчик", **fields}


def chat_json(payload: dict, *, finish_reason: str = "stop") -> httpx.Response:
    """Ответ чата, содержимое которого — объект JSON.

    Так отвечает модель везде, где от неё ждут вердикта, а не текста, и
    оборачивать словарь в строку в каждом файле тестов незачем.
    """
    return chat_response(
        json.dumps(payload, ensure_ascii=False), finish_reason=finish_reason
    )


def messages_of(request: httpx.Request) -> dict[str, str]:
    """Отправленные роли и их содержимое, разложенные по ролям.

    Чтение по номеру в списке ломалось бы от смены порядка сообщений в
    боевом коде, и падало бы обращением к несуществующему номеру вместо
    внятного несовпадения.
    """
    body = json.loads(request.content)
    return {m["role"]: m["content"] for m in body["messages"]}


def data_block(request: httpx.Request) -> str:
    """Содержимое блока данных, отправленного модели.

    Отсутствие блока названо словами: разбор по номеру дал бы `IndexError`,
    из которого не видно, что именно не так.
    """
    user = messages_of(request)["user"]
    assert "<<<\n" in user and "\n>>>" in user, "в запросе нет блока данных"
    return user.split("<<<\n", 1)[1].rsplit("\n>>>", 1)[0]


def warning_before_the_block(request: httpx.Request) -> str:
    """Что сказано модели до блока данных.

    Рамка обязана стоять **до** чужого текста: сказанное после него модель
    читает уже как продолжение данных, а не как наше указание.
    """
    user = messages_of(request)["user"]
    assert "<<<\n" in user, "в запросе нет блока данных"
    return user.split("<<<\n", 1)[0]


def chat_response(content: str | None, *, finish_reason: str = "stop") -> httpx.Response:
    """Ответ чата в форме, которую разбирает боевой код.

    `None` — не отсутствие ответа, а ответ с `"content": null`: так провайдер
    отвечает, когда модель не сказала ничего.
    """
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"content": content}, "finish_reason": finish_reason}
            ]
        },
    )
