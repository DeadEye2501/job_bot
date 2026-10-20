"""Подставной Telegraph: что отдаёт статья по адресу и о каких адресах спросили."""

from adapters import telegraph

ARTICLE = "Требования: Python"


def serve_articles(monkeypatch, answer=ARTICLE) -> list[str]:
    """Подменить загрузку статьи; в ответ — адреса, о которых спросили.

    `answer` — текст статьи на любой адрес, словарь «адрес — текст» (его можно
    наполнять и после подмены) или беда сайта, которую загрузка бросит.
    """
    asked: list[str] = []

    async def fetch_article(_client, url):
        asked.append(url)
        if isinstance(answer, Exception):
            raise answer
        return answer.get(url) if isinstance(answer, dict) else answer

    monkeypatch.setattr(telegraph, "fetch_article", fetch_article)
    return asked
