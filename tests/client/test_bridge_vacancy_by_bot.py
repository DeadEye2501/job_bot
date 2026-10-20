"""Заявки окна «Добавить вакансию», которые мост отдаёт боту.

Это текст, ссылка и поля с откликом. Отдельно от заведения полей мимо бота (`test_bridge_vacancy_create.py`): там
строка ложится в базу сразу, здесь мост отвечает «пущено», а итог приходит
вестью.
"""

from backend.flows.hand_made import HandRequest


def _requests(bot) -> list:
    return [call[1] for call in bot.calls if call[0] == "ui_ingest_by_hand"]


async def test_pasted_text_goes_to_the_bot_without_waiting_for_the_parser(
    api, ask, with_bot, told
):
    """Вставленный текст уходит боту, а окно не ждёт разбора.

    Разбор — это от двух до пяти обращений к модели: подержи мост ответ до
    конца, и окно висело бы всё это время. Человеку отвечают «пущено», а
    чем кончилось — говорят вестью.
    """
    bot = with_bot()

    answer = await ask(api.vacancies.create_from_ad, {"raw_text": "Ищем флориста"})

    assert answer["ok"]["started"] is True
    assert _requests(bot) == [HandRequest("text", "Ищем флориста", None, False)]
    # Чем кончилось, бот говорит вестью сам, до отклика; второй вести по концу
    # работы нет — исход уже сказан.
    assert await told() is None


async def test_the_named_publication_date_reaches_the_bot(api, ask, with_bot):
    """Названная дата публикации доезжает до конвейера.

    Из самого текста её не достать — в посте канала бот берёт её у Telegram, а
    у вставленного объявления взять неоткуда. Не доедь она, объявление
    выпало бы из отбора «за последние дни».
    """
    bot = with_bot()

    await ask(
        api.vacancies.create_from_ad,
        {"raw_text": "Ищем сварщика", "posted_at": "2026-08-20"},
    )

    (request,) = _requests(bot)
    assert request.posted_at.date().isoformat() == "2026-08-20"


async def test_the_switch_reaches_the_bot_as_the_window_shows_it(api, ask, with_bot):
    bot = with_bot()

    await ask(api.vacancies.create_from_ad, {"raw_text": "Ищем повара", "hands_over": True})

    (request,) = _requests(bot)
    assert request.hands_over is True


async def test_fields_to_be_handed_over_go_to_the_bot(api, ask, with_bot):
    """С включённым переключателем поля заводит бот: отклик идёт через место
    прогона. Ответ — «пущено», итог — вестью."""
    bot = with_bot()

    answer = await ask(api.vacancies.create, {"title": "Python", "hands_over": True})

    assert answer["ok"]["started"] is True
    (request,) = _requests(bot)
    assert (request.tab, request.value["title"], request.hands_over) == ("fields", "Python", True)
    listed = await ask(api.vacancies.list, {})
    assert listed["ok"]["vacancies"] == []


async def test_an_empty_paste_is_refused_with_words(api, ask, with_bot):
    """Пустую вставку отбивают словами, а не молчанием.

    Разбирать нечего, и пущенная работа кончилась бы отказом изнутри — но
    человек к этому времени уже закрыл бы окно, решив, что вакансия заводится.
    """
    with_bot()

    answer = await ask(api.vacancies.create_from_ad, {"raw_text": "   "})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Вставьте текст объявления"


async def test_a_link_goes_to_the_bot_as_it_was_pasted(api, ask, with_bot):
    """Ссылку мост отдаёт боту как есть: что за ней — пост, статья, страница, —
    решает бот один раз."""
    bot = with_bot()

    answer = await ask(api.vacancies.create_from_ad, {"url": " https://t.me/pyjobs/5 ", "hands_over": True})

    assert answer["ok"]["started"] is True
    assert _requests(bot) == [HandRequest("link", "https://t.me/pyjobs/5", None, True)]


async def test_an_empty_link_is_refused_with_words(api, ask, with_bot):
    with_bot()

    answer = await ask(api.vacancies.create_from_ad, {"url": "   "})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Вставьте ссылку на объявление"


async def test_a_page_without_claude_code_is_explained(api, ask, with_bot, heard):
    """Отказ без Claude Code говорит, что нужно, а не «не удалось»."""
    with_bot(hand_made="locked")

    await ask(api.vacancies.create_from_ad, {"url": "https://hh.ru/vacancy/1"})

    said = await heard()
    assert said["danger"] is True and "Claude Code" in said["message"]


async def test_pasting_before_the_bot_is_up_is_refused_by_name(api, ask):
    """До входа в Telegram вставку отбивают словами про бота.

    Разбор живёт на боте — там модели и место прогона. Кнопку рисуют всегда, и
    молчание на неё оставило бы человека ждать вакансию, которая не заводится.
    """
    answer = await ask(api.vacancies.create_from_ad, {"raw_text": "Ищем повара"})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Бот ещё не готов"


async def test_a_paste_the_bot_could_not_take_is_explained(api, ask, with_bot, heard):
    """Место прогона занято — человеку говорят это словами, а весть несёт метку
    заведения: окно, ждущее свою весть, иначе ждало бы вечно."""
    with_bot(hand_made="busy")

    await ask(api.vacancies.create_from_ad, {"raw_text": "Ищем повара"})

    said = await heard()
    assert said["danger"] is True and said["action"] == "create_by_hand"
