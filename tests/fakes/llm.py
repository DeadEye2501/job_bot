"""Подделка провайдера LLM: настоящий клиент поверх подставного транспорта.

Подменена только доставка. Клиент настоящий, поэтому тесты проверяют и
заголовок с ключом, и разбор ответа, и обработку кода состояния — то есть всё,
что на самом деле делает боевой код.

Незарегистрированный путь возвращает 599 с его именем в теле: забытый ответ
виден сразу и называет себя, а не превращается в загадочное падение разбора.
"""

import httpx


def provider(
    routes: dict[tuple[str, str], httpx.Response], *, api_key: str = ""
) -> httpx.AsyncClient:
    """Клиент к поддельному провайдеру. Ключ — пара «метод, путь»."""

    def handle(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        prepared = routes.get(key)
        if prepared is None:
            return httpx.Response(
                599, text=f"тест не задал ответ для {key[0]} {key[1]}"
            )
        return prepared

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    return httpx.AsyncClient(
        base_url="http://provider.test",
        headers=headers,
        transport=httpx.MockTransport(handle),
    )


def models_response(*ids: str) -> httpx.Response:
    """Ответ `/v1/models` в форме, совместимой с OpenAI."""
    return httpx.Response(200, json={"data": [{"id": one} for one in ids]})
