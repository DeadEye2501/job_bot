"""Следствия подъёма и гашения моста: что окно заводит, открываясь и закрываясь.

Предмет — жизнь хозяйства, а не то, что домены с ним делают. Проверяется здесь
то, чего не спрашивает ни один метод поверхности: проводка вестей от бота и
порядок закрытия.

**Красной фазы у этих сторожей не было.** Все четыре дописаны по находкам ревью
слайса А2.9б: восемь подписок бота стояли без единого сторожа, а закрытие входа
пропало вместе с прежней уборкой мастера. Доверие они заслужат итоговым
проходом этапа.
"""

from concurrent.futures import Future

from backend.telegram_login import LoginStep
from client.bridge import lifespan
from tests.fakes.ui_login import UiLogin


class Silent:
    """Бот, у которого нет ничего, кроме мест под обратные вызовы."""


class Stoppable(Silent):
    """Бот, который вписывает в общий список, как его просили остановиться."""

    def __init__(self, steps: list[str]) -> None:
        self.steps = steps

    def cancel_current_poll(self) -> None:
        self.steps.append("отмени обход")

    def request_stop(self) -> None:
        self.steps.append("остановись")


async def test_a_second_call_does_not_raise_a_second_bot(hub, monkeypatch):
    """Второй зов подъёма поднятого бота не трогает.

    Зовут подъём и открытие окна, и конец мастера, и удавшийся вход — а
    настройки к этому мигу уже полны. Собери он второго бота, тот сел бы на ту
    же строку сеанса: Telegram считает такие соединения разными копиями, и
    обход канала пошёл бы в два голоса.
    """
    built: list[str] = []
    monkeypatch.setattr(lifespan, "_ready_for_bot", lambda rs: True)
    monkeypatch.setattr(lifespan, "_start_bot", lambda one: built.append("собран"))
    hub.bot = Silent()

    lifespan.start_bot(hub)

    assert built == []


async def test_a_bot_still_being_built_does_not_get_a_second_one(hub, monkeypatch):
    """Собираемый бот второго тоже не пускает.

    Признака «бот есть» два: работа кладётся на мотор в потоке зовущего, а
    само поле `bot` выставляется уже внутри неё. Между этими мигами первое поле
    пусто, и заслон, смотрящий только на него, пропустил бы вторую сборку — то
    есть ровно две копии на одной строке сеанса.
    """
    built: list[str] = []
    monkeypatch.setattr(lifespan, "_ready_for_bot", lambda rs: True)
    monkeypatch.setattr(lifespan, "_start_bot", lambda one: built.append("собран"))
    hub.bot_task = Future()

    lifespan.start_bot(hub)

    assert built == []


async def test_a_fresh_login_rebuilds_the_bot(hub, monkeypatch, runner):
    """Повторный вход пересобирает бота, а не оставляет прежнего.

    Вход выдаёт новую строку сеанса, а прежнюю Telegram отзывает: бот,
    оставленный на ней, молчит до перезапуска приложения — окно при этом
    показывает связь живой.
    """
    steps: list[str] = []
    monkeypatch.setattr(lifespan, "_ready_for_bot", lambda rs: True)
    monkeypatch.setattr(lifespan, "_start_bot", lambda one: steps.append("собран"))
    old = Stoppable(steps)
    hub.bot = old

    lifespan._remember_login(hub, "маша")
    await runner.drain()

    # Порядок несущий: новый бот садится на ту же учётную запись, и собранный
    # до остановки прежнего дал бы Telegram две копии на одной строке сеанса.
    assert steps == ["отмени обход", "остановись", "собран"]
    assert hub.username_cache == "маша"


async def test_a_bot_that_did_not_stop_keeps_the_new_one_from_rising(
    hub, monkeypatch, runner
):
    """Не отпустившийся прежний бот второго поднять не даёт.

    Это и есть весь смысл пересборки одной работой: две копии на одной строке
    сеанса Telegram считает разными, и обход канала идёт в два голоса. Прежний
    при этом возвращается в хозяйство — иначе заслон подъёма увидел бы пустоту
    и пропустил следующий вход, а снос и выход остались бы без бота.
    """
    steps: list[str] = []
    monkeypatch.setattr(lifespan, "_ready_for_bot", lambda rs: True)
    monkeypatch.setattr(lifespan, "_start_bot", lambda one: steps.append("собран"))

    async def never_stops(bot, task, *args, **kwargs):
        steps.append("просили остановиться")
        return False

    monkeypatch.setattr(lifespan, "stop_bot", never_stops)
    old = Stoppable(steps)
    hub.bot = old

    lifespan._remember_login(hub, "маша")
    await runner.drain()

    assert steps == ["просили остановиться"]
    assert hub.bot is old


async def test_a_login_on_a_bare_app_does_not_build_a_bot(hub, monkeypatch):
    """Вход на ненастроенном приложении бота не поднимает.

    Первым шагом мастера идёт вход, а модели вписывают вторым и третьим:
    собранный в этот миг бот отказывает броском, и человек читает в журнале
    «бот упал» посреди того, что идёт по плану.
    """
    built: list[str] = []
    monkeypatch.setattr(lifespan, "_ready_for_bot", lambda rs: False)
    monkeypatch.setattr(lifespan, "_start_bot", lambda one: built.append("собран"))

    lifespan._remember_login(hub, None)

    assert built == []


async def test_a_bot_that_fell_does_not_stay_in_the_hub(hub, monkeypatch, runner):
    """Упавший бот в хозяйстве не остаётся.

    Оставшись, он выглядит поднятым: лампочка связи зелена, а следующий зов
    подъёма молчит, считая, что бот уже есть, — и окно живёт ширмой до
    перезапуска.
    """

    class Falling:
        def __init__(self, rs, session_factory) -> None:
            pass

        async def run(self) -> None:
            raise RuntimeError("подъём не удался")

    monkeypatch.setattr("backend.bot.client.Bot", Falling)

    lifespan._start_bot(hub)
    await runner.drain()

    assert hub.bot is None


async def test_what_the_bot_does_by_itself_reaches_the_queue(hub):
    """Всё, что бот делает сам, доезжает до страницы вестью в очереди.

    Ответа у этих вестей нет: страница о них не спрашивала. Пропади проводка,
    экран молча перестал бы узнавать про идущий обход, пришедшее письмо и
    правку списков — и никакой ошибки при этом не случилось бы.
    """
    bot = Silent()
    lifespan._tell_the_window(bot, hub)

    bot.on_cycle_start()
    bot.on_progress("разбор", "вакансия", 1, 2)
    bot.on_hr_read(7, 42)
    bot.on_channels_changed()
    bot.on_contacts_changed()
    bot.on_vacancies_changed()
    bot.on_human_needed("captcha", "site.test")
    bot.on_human_resolved()
    bot.on_round_note("обход снят")
    bot.on_cycle_end()

    news = await hub.events.take(after=0, timeout=0.01)

    assert [one["kind"] for one in news["events"]] == [
        "ingestion_started",
        "progress_update",
        "contacts_hr_read_receipt",
        # Правка каналов едет тем же родом, что и правка прочих списков: свой
        # род у неё был, а слушателя у того рода не было ни одного — свежее
        # название канала не доезжало до окна до перехода на соседний экран.
        "contacts_lists_changed",
        "contacts_lists_changed",
        "vacancies_list_changed",
        "human_needed",
        "human_resolved",
        "round_note",
        "ingestion_finished",
    ]
    assert news["events"][-4]["payload"] == {"kind": "captcha", "host": "site.test"}
    assert news["events"][-2]["payload"] == {"text": "обход снят"}


async def test_an_arrived_letter_also_moves_the_unread_count(hub):
    """Пришедшее письмо кладёт две вести: про само письмо и про счёт.

    Вниз счёт непрочитанного двигают домены — прочтение переписки кладёт ту же
    весть. Вверх его не двигало бы ничто: часов у окна больше нет, и счёт над
    списком стоял бы прежним до перезагрузки страницы.
    """
    bot = Silent()
    lifespan._tell_the_window(bot, hub)

    bot.on_new_message(7)

    news = await hub.events.take(after=0, timeout=0.01)
    assert [one["kind"] for one in news["events"]] == [
        "contacts_hr_messages_arrived",
        "unread_changed",
    ]


async def test_the_progress_of_a_cycle_travels_with_its_numbers(hub):
    """Прогресс обхода везёт с собой то, чем рисуют полосу.

    Полоса показывает, где обход и сколько осталось. Потеряй весть числа,
    полоса дёргалась бы, ничего не показывая, — а весть при этом приходила бы
    исправно.
    """
    bot = Silent()
    lifespan._tell_the_window(bot, hub)

    bot.on_progress("каналы", "python jobs", 3, 10)

    news = await hub.events.take(after=0, timeout=0.01)
    assert news["events"][0]["payload"] == {
        "stage": "каналы",
        "label": "python jobs",
        "current": 3,
        "total": 10,
    }


async def test_closing_the_window_lets_an_unfinished_login_go(hub, ask):
    """Закрытие окна закрывает недоведённый вход в Telegram.

    Посреди трёх шагов окно закрывают чаще, чем доводят их до конца. Останься
    клиент Pyrogram открытым, он пережил бы и сам мотор, а несброшенный
    отпечаток кода увёл бы следующую попытку в «код уже отправлен».
    """
    login = UiLogin(LoginStep(payload={}, error=None))
    hub.login = login

    await ask(lifespan.stop, hub)

    assert ("forget",) in login.calls
