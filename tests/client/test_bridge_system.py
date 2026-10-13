"""Следствия домена «система»: чем занят бот и что показывает нижняя полоса.

Предмет — то, что видно всегда, на любом экране: режим работы, здоровье связи,
счёт непрочитанного и счёт новых вакансий. Журнал, снос данных и обращение к рабочему столу лежат
своими файлами — их открывают нарочно, а это видно постоянно.
"""

import logging
import sys

import httpx
import pytest

from backend.app_version import VERSION
from backend.models import VacancyStatus
from tests.fakes.github_release import release_answer, serve_latest
from tests.dbio import put
from tests.factories import at, hr_row, message_row, vacancy_row


async def test_an_unknown_mode_is_refused_by_name(api, ask):
    """Незнакомый режим отбивают, назвав присланное.

    Режимов три, и приходят они строкой со страницы. Прими мост что попало —
    бот остался бы в прежнем режиме, а переключатель на экране показывал бы
    новый, и человек считал бы, что отправка включена.
    """
    answer = await ask(api.system.set_mode, "Полный вперёд")

    assert answer["fail"] == "denied"
    assert "Полный вперёд" in answer["detail"]


async def test_a_chosen_mode_comes_back_as_the_current_one(api, ask):
    """Выбранный режим возвращается тем же ответом, что рисует переключатель."""
    answer = await ask(api.system.set_mode, "DM Only")

    assert answer["ok"]["mode"] == "DM Only"


async def test_the_first_request_brings_the_whole_snapshot(api, ask):
    """Первый запрос приносит все три состояния сразу, одним ответом.

    Страница рисует нижнюю полосу целиком: здоровье, непрочитанное и режим.
    Приди одно без другого — полоса осталась бы наполовину пустой до первого
    своего опроса, то есть на секунды после открытия.
    """
    answer = await ask(api.system.initial)

    snapshot = answer["ok"]
    assert snapshot["health"]["db"] is True
    assert snapshot["unread"]["count"] == 0
    assert snapshot["mode"] == "Off"


async def test_the_version_comes_with_whether_this_copy_can_update(api, ask, monkeypatch):
    """Из исходников подменять нечего — обновиться может только собранный exe."""
    assert (await ask(api.system.version))["ok"] == {"version": VERSION, "updatable": False}

    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert (await ask(api.system.version))["ok"]["updatable"] is True


async def test_a_newer_release_is_named(api, ask, monkeypatch):
    serve_latest(monkeypatch, release_answer("v9.0.0"))

    assert (await ask(api.system.check_update))["ok"] == {"newer": "9.0.0", "trouble": None}


@pytest.mark.parametrize("answer", [
    release_answer(f"v{VERSION}"),
    release_answer("v9.0.0", asset="notes.txt"),
])
async def test_no_newer_release_names_nothing(api, ask, monkeypatch, answer):
    serve_latest(monkeypatch, answer)

    assert (await ask(api.system.check_update))["ok"] == {"newer": None, "trouble": None}


@pytest.mark.parametrize("trouble", [
    httpx.ConnectError("нет сети"),
    httpx.Response(503),
    # Портал сети Wi-Fi отвечает своей страницей и кодом 200.
    httpx.Response(200, text="<html>Войдите в сеть</html>"),
])
async def test_an_unreachable_github_is_an_answer_not_a_refusal(api, ask, monkeypatch, caplog, trouble):
    """Ответом, а не отказом: отказ окно рисует плашкой ошибки, а спека велит
    цвет сообщения — беда сети не поломка приложения. В журнал она ложится."""
    serve_latest(monkeypatch, trouble)

    with caplog.at_level(logging.WARNING, logger="client.bridge.app_update"):
        answer = await ask(api.system.check_update)

    assert answer["ok"] == {"newer": None, "trouble": "GitHub не ответил — проверьте связь."}
    assert any(r.name == "client.bridge.app_update" for r in caplog.records)


async def test_an_update_before_the_bot_is_up_is_refused_by_name(api, ask):
    """Скачивание занимает место прогона, а оно живёт в боте."""
    answer = await ask(api.system.update)

    assert (answer["fail"], answer["detail"]) == ("denied", "Бот ещё не готов.")


@pytest.fixture
def handed_over(hub):
    """Закрыто ли окно после скачивания."""
    done = []
    hub.window = type("Window", (), {"destroy": lambda self: done.append("окно закрыто")})()
    return done


async def test_a_downloaded_update_closes_the_window(api, ask, with_bot, told, handed_over):
    """Копия-подменщик ждёт выхода приложения, поэтому окно закрывается штатно,
    как крестиком: закрытие гасит бота по-хорошему."""
    bot = with_bot()

    answer = await ask(api.system.update)

    assert answer["ok"] == {"started": True, "action": "update"}
    assert await told() == {"message": "Обновление скачано — приложение перезапускается.", "danger": False}
    assert ("download_update",) in bot.calls
    assert handed_over == ["окно закрыто"]


async def test_a_copy_that_did_not_start_says_so_and_keeps_the_app(api, ask, with_bot, told, handed_over):
    with_bot(update="handoff_failed")

    await ask(api.system.update)

    assert await told() == {
        "message": "Обновление скачано, но запустить подмену не вышло — см. логи.", "danger": True,
    }
    assert handed_over == []


async def test_a_download_that_did_not_match_says_so_and_keeps_the_app(api, ask, with_bot, told, handed_over):
    with_bot(update="broken")

    await ask(api.system.update)

    assert await told() == {
        "message": "Скачанный файл не сошёлся с релизом — обновление не поставлено.", "danger": True,
    }
    assert handed_over == []


async def test_the_new_vacancies_count_is_what_apply_all_would_take(api, ask, session_factory):
    """Число на значке — ровно то, что возьмёт нажатие: разобранные New."""
    await put(session_factory, vacancy_row(), vacancy_row(),
              vacancy_row(is_parsed=False), vacancy_row(status=VacancyStatus.APPLIED))

    answer = await ask(api.system.new_vacancies)

    assert answer["ok"] == {"count": 2}


async def test_the_page_can_ask_the_queue_what_is_new(api, ask, hub):
    """Страница спрашивает очередь тем же зовом, что и всё остальное.

    Без метода поверхности очередь была бы вещью в себе: копит, ждёт, отдаёт —
    и некому спросить. Живые события до страницы не дошли бы вовсе.
    """
    hub.events.add("ingestion_started")

    answer = await ask(api.system.events, 0)

    assert [one["kind"] for one in answer["ok"]["events"]] == ["ingestion_started"]


async def test_the_page_learns_that_the_queue_is_closed(api, ask, hub):
    """Закрытую очередь страница узнаёт по ответу, а не по молчанию.

    По этому признаку её цикл и останавливается. Не доедь он до страницы, та
    спрашивала бы мост, которого уже нет, до самой смерти окна.
    """
    hub.events.close()

    answer = await ask(api.system.events, 0)

    assert answer["ok"]["closed"] is True


async def test_a_broken_number_does_not_spin_the_page_against_the_bridge(api, ask, hub):
    """Испорченный номер не заводит страницу и мост в плотную петлю.

    Кольцо считает потерянным всё старше названного номера, и на отрицательном
    объявляет потерю даже пустое. Ответ тогда приходит мгновенно, номер не
    двигается — и цикл страницы крутится без передышки, съедая ядро.

    Очередь закрыта нарочно: живая на пустой вопрос ждёт свои двадцать пять
    секунд, и сторож жёг бы их на каждом прогоне.
    """
    hub.events.close()

    answer = await ask(api.system.events, -5)

    assert answer["ok"]["missed"] is False
    assert answer["ok"]["events"] == []


async def test_a_fresh_page_is_not_told_what_happened_before_it(api, ask, hub):
    """Страница, спросившая впервые, случившегося до себя не получает.

    Номера у неё ещё нет: она только что открылась или перезагрузилась. Отдай
    ей мост кольцо с начала — окно мигнуло бы плашками часовой давности как
    свежими: «обход закончен», «письмо пришло», «отклик отправлен» — всё разом
    и всё уже неправда.

    Очередь закрыта нарочно: живая на пустой вопрос ждёт свои двадцать пять
    секунд, и сторож жёг бы их на каждом прогоне.
    """
    hub.events.add("ingestion_finished")
    hub.events.add("unread_changed")
    hub.events.close()

    answer = await ask(api.system.events, None)

    assert answer["ok"]["events"] == []
    assert answer["ok"]["missed"] is False


async def test_a_deferred_model_probe_that_broke_leaves_its_trace(
    api, ask, runner, monkeypatch, caplog
):
    """Сорвавшаяся отложенная проба моделей не пропадает молча.

    Первую пробу лампочка ждёт, а все следующие уходят в сторону — ответа у
    них не спрашивает никто. Брось такая проба поломку, лампочка показывала бы
    прошлый ответ до самого закрытия окна, а следа не осталось бы нигде: ни в
    ответе, ни в журнале.
    """
    monkeypatch.setattr("client.bridge.system._MODEL_PROBE_INTERVAL_S", 0.0)
    await ask(api.system.health)

    def fall(*_args, **_kwargs):
        raise RuntimeError("поставщик отвалился")

    monkeypatch.setattr("client.bridge.system.health.model_alive", fall)

    with caplog.at_level(logging.ERROR, logger="client.bridge.system"):
        await ask(api.system.health)
        await runner.drain()

    # След пришпилен к своему источнику: `any` по всем записям прошёл бы и от
    # чужой трассировки, случившейся в том же тесте.
    assert [
        record.name for record in caplog.records if record.exc_info
    ] == ["client.bridge.system"]
    # И к самой беде: без этого сторож был бы зелен от любой трассировки, а
    # разбирать её человеку придётся именно по тексту броска.
    assert "поставщик отвалился" in caplog.text


async def test_the_last_unread_moment_reaches_the_window_with_its_zone(api, ask, session_factory):
    """Время последнего непрочитанного приходит окну с часовым поясом.

    Без пояса окно читает время как местное, и свежее сообщение в списке над
    полосой выглядит пришедшим несколько часов назад.
    """
    hr = hr_row(name="Анна")
    await put(session_factory, hr)
    await put(session_factory, message_row(hr_id=hr.id, is_incoming=True, read_at=None, sent_at=at(50)))

    answer = await ask(api.system.unread_chats)

    assert answer["ok"]["chats"][0]["last_at"] == at(50).isoformat() + "+00:00"



async def test_ready_from_the_window_reaches_the_bot(api, ask, with_bot):
    bot = with_bot()

    answer = await ask(api.system.human_done)

    assert answer == {"ok": {}} and bot.calls == [("human_done", None)]


async def test_the_window_answer_reaches_the_bot(api, ask, with_bot):
    """Подтверждение несёт правленые пункты — они уходят боту как есть."""
    bot = with_bot()

    answer = await ask(api.system.human_done, {"items": [{"value": "правка"}]})

    assert answer == {"ok": {}} and bot.calls == [("human_done", {"items": [{"value": "правка"}]})]


async def test_switching_off_cancels_nothing(api, ask, with_bot):
    """Режим решает, что запускает автоматика; начатое Off не трогает — его
    останавливает кнопка «Стоп»."""
    bot = with_bot()

    answer = await ask(api.system.set_mode, "Off")

    assert answer == {"ok": {"mode": "Off"}}
    assert bot.calls == [("kick",)]


async def test_a_click_on_the_plate_reaches_the_bot(api, ask, with_bot):
    bot = with_bot()

    answer = await ask(api.system.reveal_browser)

    assert answer == {"ok": {}} and bot.calls == [("reveal_browser",)]
