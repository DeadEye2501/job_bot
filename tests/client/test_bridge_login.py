"""Следствия входа в Telegram: три шага, о которых окно спрашивает по одному.

Предмет — сама последовательность: код, подтверждение, облачный пароль. Шаги
объявлены в обоих окнах — и в мастере первого запуска, и в настройках, — но
тела у них общие, поэтому проверяются один раз, на том окне, где вход бывает
повторным.
"""

import json

from backend.telegram_login import LoginStep
from tests.fakes.ui_login import UiLogin


CREDENTIALS = {"api_id": 12345, "api_hash": "a" * 32, "phone": "+70000000000"}


async def test_a_request_without_credentials_is_refused(main_api, watch):
    """Без учётных данных код не запрашивают.

    Их вводят в ту же форму, и пустое поле — обычное её состояние. Уйди
    запрос без них, Telegram ответил бы отказом, из которого не видно, что
    именно человек не заполнил.
    """
    caught = watch(main_api.telegram_send_code_done)

    main_api.telegram_send_code(json.dumps({"phone": "+70000000000"}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert "Неверные поля" in answer["error"]


async def test_the_credentials_reach_the_login_in_their_own_types(main_api, watch):
    """Учётные данные доходят до входа разобранными, а не строкой из формы.

    Из окна всё приезжает текстом, а Telegram ждёт номер приложения числом.
    Уйди он строкой — библиотека отказала бы уже на соединении, и человек
    увидел бы поломку вместо понятного «проверьте api_id».
    """
    caught = watch(main_api.telegram_send_code_done)
    login = UiLogin(LoginStep(payload={"message": "Код отправлен."}, error=None))
    main_api._login = login

    main_api.telegram_send_code(json.dumps({**CREDENTIALS, "api_id": "12345"}))

    assert (await caught.next())["ok"] is True
    assert login.calls == [("send_code", 12345, "a" * 32, "+70000000000")]


async def test_a_code_before_it_was_asked_for_is_refused(main_api, watch):
    """Код, введённый до запроса, отбивают, назвав пропущенный шаг.

    Окно может остаться открытым с прошлой попытки, а попытка к тому времени
    уже закрыта. Уйди код в закрытую попытку, ответом была бы поломка
    библиотеки вместо понятного «сначала запросите код».
    """
    caught = watch(main_api.telegram_confirm_code_done)
    main_api._login = UiLogin(LoginStep(payload={}, error=None), awaiting_code=False)

    main_api.telegram_confirm_code(json.dumps({"code": "12345"}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Сначала запросите код подтверждения."


async def test_a_password_before_the_code_step_is_refused(main_api, watch):
    """Облачный пароль до шага с кодом не принимают.

    Пароль спрашивают не всегда — только если он включён у учётной записи.
    Прими мост его раньше времени, он ушёл бы в попытку, которая его не
    ждёт, и потерялся бы молча.
    """
    caught = watch(main_api.telegram_confirm_password_done)
    main_api._login = UiLogin(
        LoginStep(payload={}, error=None), awaiting_password=False
    )

    main_api.telegram_confirm_password(json.dumps({"password": "тайна"}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Сначала пройдите шаг с кодом подтверждения."


async def test_a_code_that_needs_a_password_says_so(main_api, watch):
    """Когда Telegram просит пароль, окно узнаёт об этом отдельным признаком.

    По нему открывается третий шаг формы. Приди вместо признака простое
    «готово» — окно закрыло бы вход, считая его завершённым, а сессия так и
    осталась бы несохранённой.
    """
    caught = watch(main_api.telegram_confirm_code_done)
    main_api._login = UiLogin(
        LoginStep(payload={"need_password": True}, error=None), awaiting_code=True
    )

    main_api.telegram_confirm_code(json.dumps({"code": "12345"}))

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["need_password"] is True


async def test_a_refusal_from_telegram_reaches_the_window(main_api, watch):
    """Отказ Telegram доезжает до окна своими словами.

    Неверный код и устаревший код чинятся по-разному: первый перенабирают,
    за вторым идут заново. Замени мост их общим «не получилось» — человек не
    понял бы, что делать.
    """
    caught = watch(main_api.telegram_confirm_code_done)
    main_api._login = UiLogin(
        LoginStep(payload=None, error="Код устарел — запросите новый."),
        awaiting_code=True,
    )

    main_api.telegram_confirm_code(json.dumps({"code": "12345"}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Код устарел — запросите новый."


async def test_the_password_reaches_the_login_as_typed(main_api, watch):
    """Пароль доходит до входа ровно тем, что набрали.

    Облачный пароль сверяет Telegram, и любая правка по дороге — обрезка
    пробелов, приведение регистра — превратилась бы в необъяснимый отказ на
    верном пароле.
    """
    caught = watch(main_api.telegram_confirm_password_done)
    login = UiLogin(LoginStep(payload={"done": True}, error=None), awaiting_password=True)
    main_api._login = login

    main_api.telegram_confirm_password(json.dumps({"password": " Тайна 1 "}))

    assert (await caught.next())["ok"] is True
    assert ("confirm_password", " Тайна 1 ") in login.calls


async def test_logging_out_lets_the_bot_go(main_api, watch, with_bot):
    """Выход из Telegram отвязывает бота прежде, чем стереть учётную запись.

    Бот держит ту же сессию: продолжи он работать, следующий его запрос ушёл
    бы с учётными данными, которых в настройках уже нет, и упал бы где-то
    посреди опроса каналов.
    """
    caught = watch(main_api.system_telegram_logout_done)
    main_api._login = UiLogin(LoginStep(payload={}, error=None))
    bot = with_bot()

    main_api.request_telegram_logout()

    assert (await caught.next())["ok"] is True
    assert ("log_out_session",) in bot.calls
    assert main_api._bot is None
