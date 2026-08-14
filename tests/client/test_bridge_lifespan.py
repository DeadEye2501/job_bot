"""Следствия подъёма и гашения моста: что окно заводит, открываясь и закрываясь.

Предмет — жизнь хозяйства, а не то, что домены с ним делают. Проверяется здесь
то, чего не спрашивает ни один метод поверхности: проводка вестей от бота и
порядок закрытия.

**Красной фазы у этих сторожей не было.** Все четыре дописаны по находкам ревью
слайса А2.9б: восемь подписок бота стояли без единого сторожа, а закрытие входа
пропало вместе с прежней уборкой мастера. Доверие они заслужат итоговым
проходом этапа.
"""

from backend.telegram_login import LoginStep
from client.bridge import lifespan
from tests.fakes.ui_login import UiLogin


class Silent:
    """Бот, у которого нет ничего, кроме мест под обратные вызовы."""


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
    bot.on_cycle_end()

    news = await hub.events.take(after=0, timeout=0.01)

    assert [one["kind"] for one in news["events"]] == [
        "ingestion_started",
        "progress_update",
        "contacts_hr_read_receipt",
        "contacts_channels_changed",
        "contacts_lists_changed",
        "vacancies_list_changed",
        "ingestion_finished",
    ]


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
