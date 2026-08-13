"""Следствие удаления всех данных: что успевает случиться до самого удаления.

**Дальше первого шага этот слот в тестах не пускают, и это не осторожность, а
необходимость.** Он удаляет файл базы из каталога данных — а в прогоне каталог
подменён на временный, и там лежит та самая база, которую стенд поднял на всю
сессию. Дай ему доработать — следующие тесты остались бы без базы. Кончается он
к тому же выходом из процесса (`os._exit`), то есть убил бы и сам прогон.

Наблюдаемое здесь — порядок: до того как что-то удалять, слот отвязывает бота
и гасит таймеры. Это и есть его первый шаг, и он синхронный.
"""

from concurrent.futures import Future

import pytest


@pytest.fixture
def held_back(main_api, monkeypatch):
    """Ловит работу, не давая ей начаться.

    Корутину закрываем сразу: незапущенная она подняла бы предупреждение, а
    предупреждения в этом прогоне равны ошибкам.
    """
    caught = []

    def _hold(coro):
        coro.close()
        caught.append(coro)
        return Future()

    monkeypatch.setattr(main_api._runner, "submit", _hold)
    return caught


async def test_the_bot_is_let_go_before_anything_is_deleted(
    main_api, with_bot, held_back
):
    """Бот отвязывается и таймеры гаснут до того, как начнётся удаление.

    Таймеры ходят в базу каждые несколько секунд, а бот держит её открытой.
    Сработай любой из них посреди удаления — файл базы оказался бы занят, а
    в журнал полетели бы поломки на пустом месте, и человек решил бы, что
    удаление не удалось.
    """
    with_bot()

    main_api.request_delete_all_data()

    assert main_api._bot is None
    assert main_api._health_timer.isActive() is False
    assert main_api._unread_timer.isActive() is False
    assert len(held_back) == 1
