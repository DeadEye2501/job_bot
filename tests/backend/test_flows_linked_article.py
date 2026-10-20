"""Следствия, которые наблюдает тест `backend/flows/linked_article.py`.

Само хождение в сеть проверено у переходника (`test_adapters_telegraph`); здесь
смотрят на склейку — что дописано, в каком порядке и когда в сеть не ходят
вовсе — и на чтение поста, которое её зовёт.
"""

import logging

import httpx
import pytest

from backend.flows import linked_article
from tests.fakes.telegram_objects import post
from tests.fakes.telegraph import serve_articles


@pytest.fixture
def fetched(monkeypatch):
    """Подставная загрузка статьи: отдаёт заготовленное и помнит, о чём просили."""
    articles: dict[str, str | None] = {}
    return serve_articles(monkeypatch, articles), articles


async def test_the_article_is_written_after_the_post(fetched):
    """Статья дописывается за текстом поста, а не вместо него."""
    asked, articles = fetched
    articles["https://telegra.ph/QA-08-21"] = "Требования: Python"

    got, whole = await linked_article.with_linked_articles(
        "Senior QA https://telegra.ph/QA-08-21"
    )

    assert got == "Senior QA https://telegra.ph/QA-08-21\n\nТребования: Python"
    assert asked == ["https://telegra.ph/QA-08-21"]
    assert whole is True


async def test_a_post_reads_out_with_its_articles(fetched):
    """Текст поста — со статьями: одно чтение на приём и на прогон заново,
    иначе разобранное кнопкой разошлось бы с разобранным обходом."""
    _asked, articles = fetched
    articles["https://telegra.ph/QA-08-21"] = "Требования: Python"

    got = await linked_article.post_full_text(post(10, text="Senior QA https://telegra.ph/QA-08-21"))

    assert got == ("Senior QA https://telegra.ph/QA-08-21\n\nТребования: Python", True)


async def test_a_post_without_text_reads_out_as_nothing(fetched):
    """Пост с одной картинкой текста не даёт — читать в нём нечего."""
    assert await linked_article.post_full_text(post(10, text="")) is None


async def test_a_post_without_articles_does_not_go_online(fetched):
    """Без ссылки на статью в сеть не ходят вовсе."""
    asked, _articles = fetched

    got, whole = await linked_article.with_linked_articles("Ищем Python-разработчика")

    assert got == "Ищем Python-разработчика"
    assert asked == []
    assert whole is True


async def test_one_address_is_fetched_once(fetched):
    """Один адрес скачивается один раз, сколько бы раз ни встретился.

    В посте он встречается дважды — словами и подписью кнопки, — и без этого
    статья дописалась бы к объявлению вторым разом.
    """
    asked, articles = fetched
    articles["https://telegra.ph/QA-08-21"] = "Требования: Python"

    got, _whole = await linked_article.with_linked_articles(
        "https://telegra.ph/QA-08-21 ПОСМОТРЕТЬ (https://telegra.ph/QA-08-21)"
    )

    assert asked == ["https://telegra.ph/QA-08-21"]
    assert got.count("Требования: Python") == 1


async def test_articles_are_written_in_the_order_they_are_linked(fetched):
    """Несколько статей дописываются в том порядке, в каком на них сослались."""
    asked, articles = fetched
    articles["https://telegra.ph/first-08-21"] = "первая"
    articles["https://telegra.ph/second-08-21"] = "вторая"

    got, _whole = await linked_article.with_linked_articles(
        "тут https://telegra.ph/first-08-21 и тут https://telegra.ph/second-08-21"
    )

    assert asked == ["https://telegra.ph/first-08-21", "https://telegra.ph/second-08-21"]
    assert got.endswith("\n\nпервая\n\nвторая")


async def test_an_address_without_an_article_leaves_the_text_whole(fetched):
    """Адрес, за которым статьи нет, недобором не считается.

    Её снесли или за ключом ничего нет — второй раз лучше не
    станет. Считай это недобором, и прогон заново у такой вакансии перестал
    бы обновлять текст навсегда.
    """
    asked, _articles = fetched

    got, whole = await linked_article.with_linked_articles(
        "Senior QA https://telegra.ph/QA-08-21"
    )

    assert asked == ["https://telegra.ph/QA-08-21"]
    assert got == "Senior QA https://telegra.ph/QA-08-21"
    assert whole is True


async def test_a_site_that_did_not_answer_makes_the_text_short(monkeypatch):
    """Не отдавшаяся страница — недобор: к утру она вернётся.

    Признаётся ради прогона заново: у него на руках уже есть сохранённый
    текст со статьёй, и переписать его постом без неё — потерять требования.
    """
    serve_articles(monkeypatch, httpx.ConnectError("сеть отвалилась"))

    got, whole = await linked_article.with_linked_articles(
        "Senior QA https://telegra.ph/QA-08-21"
    )

    assert got == "Senior QA https://telegra.ph/QA-08-21"
    assert whole is False


async def test_the_log_names_what_the_site_answered_with(monkeypatch, caplog):
    """Запись о несостоявшейся статье называет породу беды, а не пустые скобки.

    От породы зависит судьба объявления: истёкший срок ожидания пройдёт, а
    закрытая дверь сайта — нет. У истёкшего срока `str` пуст, и запись «не
    отдал страницу ()» не отличает одно от другого ничем.
    """
    serve_articles(monkeypatch, httpx.ReadTimeout(""))

    with caplog.at_level(logging.WARNING):
        await linked_article.with_linked_articles("Senior QA https://telegra.ph/QA-08-21")

    assert "ReadTimeout" in caplog.text


async def test_no_more_than_three_articles_are_fetched(fetched):
    """Больше трёх статей с одного объявления не тянут, и это не недобор.

    Пост-дайджест «десять вакансий недели» ссылается на статью у каждой, и
    десять походов в сеть подряд держат обход канала на себе. Разбирать такой
    пост как одну вакансию всё равно нечего.

    Недобором срез не считается: четвёртая ссылка никуда не денется и завтра,
    а прогон заново у такого объявления перестал бы обновлять текст навсегда.
    """
    asked, articles = fetched
    text = " ".join(f"https://telegra.ph/QA-{n}-08-21" for n in range(6))

    _got, whole = await linked_article.with_linked_articles(text)

    assert len(asked) == 3
    assert whole is True
