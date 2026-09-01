"""Следствия одного оборота главного цикла бота.

Оборот делает разное в зависимости от режима: выключенный не догоняет
пропущенное, не проверяет молчание HR и не ходит по каналам; «только личные»
делает первые два; полный — всё. Переход в рабочий режим и из него отмечается
особо: при входе догоняются пропущенные письма, при выходе сливается текст,
ждавший разбора.

Выход из цикла закрывает за собой: ставит признак остановки до того, как
отключить клиента, гасит отложенные разборы и закрывает соединения с
языковой моделью. Пропущенное здесь означает работу, которая переживёт
бота и полезет в закрытые соединения.
"""

import asyncio

import pytest

from backend.bot import loop as loop_mod
from backend.models import BotMode
from tests.fakes.ingestion import FakeIngestion, wire


@pytest.fixture
def caught_up(monkeypatch):
    """Подменяет догон пропущенных писем: он живёт в конвейере."""
    calls: list[dict] = []

    async def catch_up_missed_dms(client, *args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("backend.bot.loop.catch_up_missed_dms", catch_up_missed_dms)
    return calls


async def _one_turn(chatting, mode, ingestion=None):
    """Бот в заданном режиме, сделавший ровно один оборот цикла."""
    bot, client, _ = await chatting(mode=mode)
    pipeline = ingestion if ingestion is not None else FakeIngestion()
    wire(bot, pipeline)

    await bot.run(once=True)

    return bot, client, pipeline


async def test_a_turn_starts_and_stops_the_telegram_client(chatting, caught_up):
    """Оборот поднимает клиента Telegram и отключает его за собой."""
    bot, client, _ = await _one_turn(chatting, BotMode.OFF)

    assert client.lifecycle == ["запуск", "остановка"]


async def test_the_bot_becomes_ready_only_after_the_client_starts(
    chatting, caught_up
):
    """Готовность объявляется после подключения клиента, а не до.

    До этого мига обращение из окна попало бы в полусобранное состояние.
    Смотрим оба края подъёма: сам `client.start` и первую работу оборота сразу
    за ним — подбор недоразобранного, которым начинается приём.
    """
    bot, client, _ = await chatting(mode=BotMode.FULL)
    pipeline = FakeIngestion()
    wire(bot, pipeline)
    seen: list[bool] = []

    async def start():
        seen.append(bot.is_ready)
        client.lifecycle.append("запуск")

    recover = pipeline.recover_orphan_vacancies

    async def recover_and_look():
        seen.append(bot.is_ready)
        return await recover()

    client.start = start
    pipeline.recover_orphan_vacancies = recover_and_look

    await bot.run(once=True)

    assert seen == [False, True]


async def test_a_bot_that_left_the_loop_is_not_ready_any_more(chatting, caught_up):
    """Вышедший из цикла бот готовым больше не считается.

    Готовность спрашивает лампочка связи в окне. Останься она истиной после
    выхода, человек видел бы зелёный огонёк у бота, который уже отключил
    клиента и закрыл соединения с моделью.
    """
    bot, _, _ = await _one_turn(chatting, BotMode.OFF)

    assert bot.is_ready is False


async def test_a_turn_picks_up_vacancies_left_half_parsed(chatting, caught_up):
    """Каждый полный оборот подбирает недоразобранное до того, как идти за новым.

    Недоразобранной строка остаётся не только от обрыва: объявление, чья
    статья по ссылке не пришла, ждёт приговора и в списке невидимо. Подбирай
    его один раз при запуске — и оно ждало бы до следующего запуска
    приложения, а работает оно сутками.
    """
    _, _, pipeline = await _one_turn(chatting, BotMode.FULL)

    assert pipeline.log.index("недоразобранные") < pipeline.log.index("прогон каналов")


async def test_a_switched_off_turn_picks_up_nothing(chatting, caught_up):
    """Выключенный бот недоразобранное не подбирает.

    Подбор кончается разбором и отправкой отклика, а в Off бот не делает
    ни того, ни другого: он на паузе.
    """
    _, _, pipeline = await _one_turn(chatting, BotMode.OFF)

    assert "недоразобранные" not in pipeline.log


async def test_a_failed_recovery_does_not_stop_the_turn(chatting, caught_up):
    """Сбой подбора недоразобранного оборот не отменяет."""
    pipeline = FakeIngestion()
    pipeline.recovery_error = RuntimeError("сорвалось")

    _, client, _ = await _one_turn(chatting, BotMode.FULL, pipeline)

    assert "прогон каналов" in pipeline.log
    assert client.lifecycle == ["запуск", "остановка"]


async def test_a_switched_off_bot_does_nothing_but_start_and_stop(
    chatting, caught_up
):
    """Выключенный бот за оборот ничего не делает, кроме как поднимается.

    Ни догона пропущенного, ни проверки молчания, ни хода по каналам:
    «выключен» — это полная остановка, а не тихий режим.
    """
    _, _, pipeline = await _one_turn(chatting, BotMode.OFF)

    assert caught_up == []
    assert "молчание" not in pipeline.log
    assert "прогон каналов" not in pipeline.log


async def test_entering_an_active_mode_catches_up_missed_letters(
    chatting, caught_up, turn_and_settle
):
    """Вход в рабочий режим догоняет пропущенные письма.

    Бот стартует из выключенного состояния, и всё, что HR писал, пока
    приложение было закрыто, иначе осталось бы непрочитанным.

    Догон идёт задачей, поэтому оборота мало: ждать надо того мига, когда
    цикл дал ей ход.
    """
    bot, _, _ = await chatting(mode=BotMode.DM_ONLY)
    wire(bot, FakeIngestion())

    await turn_and_settle(bot, BotMode.DM_ONLY)

    assert len(caught_up) == 1


async def test_a_failed_catch_up_does_not_stop_the_turn(chatting, monkeypatch):
    """Сбой догона пропущенного оборот не отменяет."""

    async def catch_up_missed_dms(client, *args, **kwargs):
        raise OSError("сеть")

    monkeypatch.setattr("backend.bot.loop.catch_up_missed_dms", catch_up_missed_dms)

    _, client, pipeline = await _one_turn(chatting, BotMode.FULL)

    assert "прогон каналов" in pipeline.log
    assert client.lifecycle == ["запуск", "остановка"]


async def test_an_active_turn_checks_for_silent_hrs(chatting, caught_up):
    """В рабочем режиме оборот проверяет, кто из HR замолчал."""
    _, _, pipeline = await _one_turn(chatting, BotMode.DM_ONLY)

    assert "молчание" in pipeline.log


async def test_a_failed_silence_check_does_not_stop_the_turn(chatting, caught_up):
    """Сбой проверки молчания оборот не отменяет."""
    pipeline = FakeIngestion()
    pipeline.ghosting_error = RuntimeError("сорвалось")

    _, client, _ = await _one_turn(chatting, BotMode.FULL, pipeline)

    assert "прогон каналов" in pipeline.log
    assert client.lifecycle == ["запуск", "остановка"]


async def test_only_the_full_mode_walks_the_channels(chatting, caught_up):
    """По каналам ходит только полный режим.

    «Только личные» отвечает на письма HR, но сам вакансий не ищет — это
    и есть разница между двумя рабочими режимами.
    """
    _, _, pipeline = await _one_turn(chatting, BotMode.DM_ONLY)

    assert "прогон каналов" not in pipeline.log


async def test_a_full_turn_walks_the_channels(chatting, caught_up):
    """Полный режим за оборот проходит по каналам."""
    _, _, pipeline = await _one_turn(chatting, BotMode.FULL)

    assert pipeline.full_calls == 1


async def test_a_running_manual_poll_is_not_clobbered(chatting, caught_up, busy_slot):
    """Идущий ручной прогон оборотом не перебивается.

    Иначе два цикла крутились бы разом и дрались за кэш векторов и
    курсоры каналов.
    """
    bot, client, _ = await chatting(mode=BotMode.FULL)
    pipeline = FakeIngestion()
    wire(bot, pipeline)
    busy_slot(bot)

    await bot.run(once=True)

    assert pipeline.full_calls == 0


async def test_the_window_hears_both_ends_of_a_full_turn(chatting, caught_up):
    """Окно узнаёт о начале и конце цикла, пройденного самим ботом."""
    bot, client, _ = await chatting(mode=BotMode.FULL)
    wire(bot, FakeIngestion())
    heard: list[str] = []
    bot.on_cycle_start = lambda: heard.append("начало")
    bot.on_cycle_end = lambda: heard.append("конец")

    await bot.run(once=True)

    assert heard == ["начало", "конец"]


async def test_a_failed_poll_does_not_stop_the_turn(chatting, caught_up):
    """Сбой прохода по каналам оборот не роняет и место освобождает."""
    pipeline = FakeIngestion(error=RuntimeError("сорвалось"))

    bot, client, _ = await _one_turn(chatting, BotMode.FULL, pipeline)

    assert bot.current_poll_task is None
    assert client.lifecycle == ["запуск", "остановка"]


async def test_leaving_the_loop_marks_the_shutdown_before_disconnecting(
    chatting, caught_up
):
    """Признак остановки ставится до отключения клиента.

    Обработчик, отстреливший уже после разборки, увидит признак и ничего
    не сделает — вместо того чтобы лезть в закрытые соединения.
    """
    _, _, pipeline = await _one_turn(chatting, BotMode.OFF)

    assert pipeline.log[-2:] == ["гасим", "отмена разбора"]


async def test_leaving_the_loop_closes_both_model_connections(make_bot, caught_up):
    """Выход из цикла закрывает оба соединения с языковой моделью.

    Соединений два, когда чат и векторы живут на разных адресах. Забытое
    открытым переживает бота и держит гнездо до конца работы приложения.
    """
    bot = wire(await make_bot(embed_url="http://векторы.test"), FakeIngestion())
    assert bot.lm_embed_client is not bot.lm_client

    await bot.run(once=True)

    assert bot.lm_client.closed == 1
    assert bot.lm_embed_client.closed == 1


async def test_a_shared_model_connection_is_closed_once(chatting, caught_up):
    """Общее соединение закрывается один раз, а не дважды.

    Чат и векторы делят его, когда совпали адрес и ключ; второе закрытие
    было бы обращением к уже закрытому.
    """
    bot, client, _ = await chatting()
    wire(bot, FakeIngestion())
    assert bot.lm_client is bot.lm_embed_client

    await bot.run(once=True)

    assert bot.lm_client.closed == 1


async def test_an_already_disconnected_client_is_not_a_failure(chatting, caught_up):
    """Уже отключённый клиент разборку не роняет.

    После выхода из учётной записи Pyrogram отключается сам, и повторная
    остановка отвечает отказом — но соединения с моделью закрыть надо.
    """
    from tests.fakes.telegram import FakeTelegramClient

    bot, client, _ = await chatting(
        client=FakeTelegramClient(fails={"stop": ConnectionError("уже отключён")})
    )
    wire(bot, FakeIngestion())

    await bot.run(once=True)

    assert bot.lm_client.closed == 1


async def test_a_broken_disconnect_does_not_leave_connections_open(
    chatting, caught_up
):
    """Сорвавшееся отключение клиента соединений открытыми не оставляет."""
    from tests.fakes.telegram import FakeTelegramClient

    bot, client, _ = await chatting(
        client=FakeTelegramClient(fails={"stop": OSError("сеть")})
    )
    wire(bot, FakeIngestion())

    await bot.run(once=True)

    assert bot.lm_client.closed == 1


async def test_a_connection_that_never_came_up_still_closes_the_rest(
    chatting, caught_up
):
    """Сорвавшийся подъём соединения оставляет соединения с моделью закрытыми.

    Клиент Telegram не поднялся — сеть, отозванный ключ, занятый порт, — а два
    клиента модели уже открыты: собирают их до подъёма. Пройди подъём мимо
    разборки, они пережили бы бота и держали бы гнёзда до конца работы
    приложения.
    """
    from tests.fakes.telegram import FakeTelegramClient

    bot, client, _ = await chatting(
        client=FakeTelegramClient(fails={"start": OSError("сеть")})
    )
    wire(bot, FakeIngestion())

    with pytest.raises(OSError):
        await bot.run(once=True)

    assert bot.lm_client.closed == 1


async def test_switching_off_drains_the_text_waiting_to_be_read(
    chatting, caught_up, monkeypatch
):
    """Выключение сливает текст, ждавший разбора.

    Разбор откладывается на минуту после последнего письма. Выключенный
    бот статусов не меняет — значит и отложенное решение принимать не
    должен, иначе оно сработает уже после того, как его попросили
    остановиться.
    """
    bot, client, _ = await chatting(mode=BotMode.FULL)
    pipeline = FakeIngestion()
    wire(bot, pipeline)
    # Секунда, а не ноль: нулевой интервал больше не берётся — он крутил бы
    # цикл опроса встык, и настройки такое теперь откатывают к умолчанию.
    await bot.rs.set_app("poll_interval_sec", "1")

    # Останов повешен на чтение режима, а не на сам слив: слив здесь —
    # предмет проверки, и если бы цикл кончался им, снятая строка вешала бы
    # прогон вместо того, чтобы покрасить тест.
    modes = [BotMode.FULL]

    async def next_mode(session):
        if modes:
            return modes.pop(0)
        # Просьба об остановке идёт тем же вызовом, что отдаёт «выключено»:
        # лишний оборот досиживал бы интервал опроса целиком.
        bot.request_stop()
        return BotMode.OFF

    monkeypatch.setattr(loop_mod, "read_mode", next_mode)

    await bot.run()

    assert pipeline.drains == 1


async def test_a_stop_request_ends_the_loop_after_the_current_turn(
    chatting, caught_up
):
    """Просьба остановиться заканчивает цикл после текущего оборота.

    Без неё цикл ушёл бы в получасовой сон и вышел бы только к его концу.
    """
    bot, client, _ = await chatting(mode=BotMode.FULL)
    pipeline = FakeIngestion()
    wire(bot, pipeline)
    bot.request_stop()

    await bot.run()

    assert pipeline.full_calls == 1
    assert client.lifecycle == ["запуск", "остановка"]


async def test_a_kick_during_the_turn_is_not_lost(chatting, caught_up):
    """Окрик из окна, пришедший во время оборота, не пропадает.

    Тумблер режима будит цикл, чтобы тот сразу увидел смену: при уходе в OFF
    — слил накопленную переписку в разбор, при возврате — догнал пропущенное.
    Гасись событие перед ожиданием, окрик, поданный пока шёл обход каналов,
    стирался бы, и цикл спал бы полный срок — по умолчанию полчаса, а на
    настроенных полутора часах и дольше.
    """
    import asyncio

    bot, _client, _hr = await chatting()
    bot.wake_event.set()

    # Срок ожидания здесь не при чём: с сохранённым окриком возврат мгновенный,
    # а потерянный окрик усыпил бы цикл на весь настроенный интервал.
    await asyncio.wait_for(loop_mod._sleep_until_wake(bot), timeout=1)

    assert not bot.wake_event.is_set()


async def test_a_hanging_catch_up_does_not_hold_the_turn(chatting, monkeypatch):
    """Догон переписки оборот не держит.

    Стоял он в теле цикла с `await`, до срока молчания, до обхода каналов и до
    проверки остановки: пока он шёл — а на холодном кэше это были минуты, —
    приложение не закрывалось и кнопка «остановить» не помогала.
    """
    async def catch_up_missed_dms(client, *args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr("backend.bot.loop.catch_up_missed_dms", catch_up_missed_dms)
    bot, _, _ = await chatting(mode=BotMode.DM_ONLY)
    pipeline = FakeIngestion()
    wire(bot, pipeline)

    await asyncio.wait_for(bot.run(once=True), timeout=5)

    assert "молчание" in pipeline.log

