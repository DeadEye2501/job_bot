"""Следствие удаления всех данных: в каком порядке это происходит.

**Дальше первого шага домен в тестах не пускают, и это не осторожность, а
необходимость.** Он удаляет файл базы из каталога данных — а в прогоне каталог
подменён на временный, и там лежит та самая база, которую стенд поднял на всю
сессию. Дай ему доработать — следующие тесты остались бы без базы. Кончается он
к тому же выходом из процесса, то есть убил бы и сам прогон.

Наблюдаемое здесь — порядок: бота отвязывают до того, как что-то удалять, а из
процесса уходят после того, как снос кончился.
"""

import pytest

from tests.fakes.ui_bot import UiBot


@pytest.fixture
def wipe_steps(monkeypatch, hub):
    """Записывает шаги сноса вместо того, чтобы их делать.

    Снос и выход подменены оба: первый снёс бы базу, на которой стоит весь
    прогон, второй убил бы сам прогон. Каждый шаг называет себя и говорит,
    отвязан ли к этому мигу бот.
    """
    steps: list[tuple] = []

    async def _wipe_all(engine) -> list[str]:
        steps.append(("снос", hub.bot))
        return []

    monkeypatch.setattr("client.bridge.wipe.wipe_all", _wipe_all)
    monkeypatch.setattr("client.bridge.wipe.forget_master_key", lambda: None)
    monkeypatch.setattr(
        "client.bridge.wipe._leave_later", lambda: steps.append(("выход", hub.bot))
    )
    return steps


async def test_the_key_stays_when_something_survived_the_wipe(api, ask, monkeypatch):
    """Ключ забывают только после удавшегося сноса.

    Главный ключ открывает всё, что зашифровано в базе. Забытый при живой базе,
    он оставляет человека с целыми данными, которых уже никто не прочтёт: ни
    строки сессии Telegram, ни ключей провайдера — а снос при этом не удался, и
    приложение продолжает работать.
    """
    forgotten: list[str] = []

    async def _wipe_all(engine) -> list[str]:
        return ["jobbot.db: занят другим процессом"]

    monkeypatch.setattr("client.bridge.wipe.wipe_all", _wipe_all)
    monkeypatch.setattr(
        "client.bridge.wipe.forget_master_key", lambda: forgotten.append("забыт")
    )
    monkeypatch.setattr("client.bridge.wipe._leave_later", lambda: None)

    answer = await ask(api.system.wipe)

    assert answer["fail"] == "denied"
    assert forgotten == []


async def test_the_refusal_says_one_phrase_instead_of_the_system_troubles(
    api, ask, monkeypatch
):
    """Не удавшийся снос отвечают одной фразой, а не бедами от системы.

    Беды приходят строками от Windows: код `WinError`, полный путь к файлу и
    одна и та же причина по разу на каждый занятый файл — база и оба её
    спутника. Человеку это три экрана текста об одном: файлы кто-то держит, и
    закрыть надо чужую программу, а не разбирать их по именам.

    Сами беды не пропадают: каждую пишет `backend.wipe`, и до перезапуска их
    видно на экране «Логи».
    """

    async def _wipe_all(engine) -> list[str]:
        busy = "[WinError 32] Процесс не может получить доступ к файлу"
        return [
            f"jobbot.db: {busy}: 'C:\\Users\\deade\\JobBot\\jobbot.db'",
            f"jobbot.db-wal: {busy}: 'C:\\Users\\deade\\JobBot\\jobbot.db-wal'",
        ]

    monkeypatch.setattr("client.bridge.wipe.wipe_all", _wipe_all)
    monkeypatch.setattr("client.bridge.wipe.forget_master_key", lambda: None)
    monkeypatch.setattr("client.bridge.wipe._leave_later", lambda: None)

    answer = await ask(api.system.wipe)

    assert answer["detail"] == (
        "Файлы открыты в другом процессе и не могут быть удалены."
    )


async def test_the_answer_is_ready_before_the_bot_and_the_data_are_gone(
    api, ask, with_bot, wipe_steps
):
    """Бота отвязывают до удаления, а сторож выхода заводят после него.

    Бот держит базу открытой: сработай его обход посреди удаления — файл
    оказался бы занят, и Windows не дала бы его снести. А сторож выхода
    заводится последним шагом самой работы: заведи его раньше, у возврата, — и
    он срубил бы процесс посреди наполовину снесённого каталога, потому что
    возврат случается и по сроку, и по отмене.
    """
    with_bot()

    answer = await ask(api.system.wipe)

    assert "ok" in answer
    assert wipe_steps == [("снос", None), ("выход", None)]


async def test_the_bot_is_let_go_before_the_work_is_sent_off(
    api, ask, hub, wipe_steps, monkeypatch
):
    """Бота отвязывают до того, как работа уходит на мотор.

    Между отправкой работы и её началом окно живёт своей жизнью: соседний зов
    в этот миг взял бы полуостановленного бота и пошёл бы с ним в базу, которой
    вот-вот не станет.

    Сторож смотрит на миг отправки, а не внутрь работы. Изнутри бот обнулён в
    любом случае — потому соседний сторож выше и остаётся зелёным, если
    обнуление перенести внутрь; отсюда же такой перенос виден.

    Красной фазы не было: дописан по находке ревью, доверие заслужит итоговым
    проходом.
    """
    # Бот и его работа ставятся руками, а не фикстурой: без них сторож зелен
    # впустую — обнулять было бы нечего.
    hub.bot = UiBot()
    hub.bot_task = object()
    at_submit: list = []
    sending = hub.runner.submit

    def watched(coro):
        # Пара, а не один бот: обнуляются они вместе и по одной причине, и
        # забытая половина оставила бы соседу работу уже остановленного.
        at_submit.append((hub.bot, hub.bot_task))
        return sending(coro)

    monkeypatch.setattr(hub.runner, "submit", watched)

    await ask(api.system.wipe)

    assert at_submit == [(None, None)]
