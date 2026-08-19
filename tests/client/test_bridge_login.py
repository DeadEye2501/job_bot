"""Следствия входа в Telegram: три шага, о которых окно спрашивает по одному.

Предмет — сама последовательность: код, подтверждение, облачный пароль. Шаги
одни и те же, откуда бы в них ни вошли — с первого запуска или из настроек:
написаны они один раз (`client/bridge/login.py`), и второго написания больше
нет.
"""

from backend.telegram_login import LoginStep
from backend.crypto import encrypt_bytes, encrypt_str
from tests.dbio import put
from tests.factories import tg_account_row
from tests.fakes.ui_login import UiLogin


CREDENTIALS = {"api_id": 12345, "api_hash": "a" * 32, "phone": "+70000000000"}


async def test_a_request_without_credentials_is_refused(api, ask):
    """Без учётных данных код не запрашивают.

    Их вводят в ту же форму, и пустое поле — обычное её состояние. Уйди
    запрос без них, Telegram ответил бы отказом, из которого не видно, что
    именно человек не заполнил.
    """
    answer = await ask(api.settings.send_code, {"phone": "+70000000000"})

    assert answer["fail"] == "fields"
    assert "Неверные поля" in answer["detail"]


async def test_the_credentials_reach_the_login_in_their_own_types(api, ask, hub):
    """Учётные данные доходят до входа разобранными, а не строкой из формы.

    Из окна всё приезжает текстом, а Telegram ждёт номер приложения числом.
    Уйди он строкой — библиотека отказала бы уже на соединении, и человек
    увидел бы поломку вместо понятного «проверьте api_id».
    """
    login = UiLogin(LoginStep(payload={"message": "Код отправлен."}, error=None))
    hub.login = login

    answer = await ask(api.settings.send_code, {**CREDENTIALS, "api_id": "12345"})

    assert "ok" in answer
    assert login.calls == [("send_code", 12345, "a" * 32, "+70000000000")]


async def test_a_code_before_it_was_asked_for_is_refused(api, ask, hub):
    """Код, введённый до запроса, отбивают, назвав пропущенный шаг.

    Окно может остаться открытым с прошлой попытки, а попытка к тому времени
    уже закрыта. Уйди код в закрытую попытку, ответом была бы поломка
    библиотеки вместо понятного «сначала запросите код».
    """
    hub.login = UiLogin(LoginStep(payload={}, error=None), awaiting_code=False)

    answer = await ask(api.settings.confirm_code, {"code": "12345"})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Сначала запросите код подтверждения."


async def test_a_password_before_the_code_step_is_refused(api, ask, hub):
    """Облачный пароль до шага с кодом не принимают.

    Пароль спрашивают не всегда — только если он включён у учётной записи.
    Прими мост его раньше времени, он ушёл бы в попытку, которая его не
    ждёт, и потерялся бы молча.
    """
    hub.login = UiLogin(LoginStep(payload={}, error=None), awaiting_password=False)

    answer = await ask(api.settings.confirm_password, {"password": "тайна"})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Сначала пройдите шаг с кодом подтверждения."


async def test_a_code_that_needs_a_password_says_so(api, ask, hub):
    """Когда Telegram просит пароль, окно узнаёт об этом отдельным признаком.

    По нему открывается третий шаг формы. Приди вместо признака простое
    «готово» — окно закрыло бы вход, считая его завершённым, а сессия так и
    осталась бы несохранённой.
    """
    hub.login = UiLogin(
        LoginStep(payload={"need_password": True}, error=None), awaiting_code=True
    )

    answer = await ask(api.settings.confirm_code, {"code": "12345"})

    assert answer["ok"]["need_password"] is True


async def test_a_refusal_from_telegram_reaches_the_window(api, ask, hub):
    """Отказ Telegram доезжает до окна своими словами.

    Неверный код и устаревший код чинятся по-разному: первый перенабирают,
    за вторым идут заново. Замени мост их общим «не получилось» — человек не
    понял бы, что делать.
    """
    hub.login = UiLogin(
        LoginStep(payload=None, error="Код устарел — запросите новый."),
        awaiting_code=True,
    )

    answer = await ask(api.settings.confirm_code, {"code": "12345"})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Код устарел — запросите новый."


async def test_the_password_reaches_the_login_as_typed(api, ask, hub):
    """Пароль доходит до входа ровно тем, что набрали.

    Облачный пароль сверяет Telegram, и любая правка по дороге — обрезка
    пробелов, приведение регистра — превратилась бы в необъяснимый отказ на
    верном пароле.
    """
    login = UiLogin(LoginStep(payload={"done": True}, error=None), awaiting_password=True)
    hub.login = login

    answer = await ask(api.settings.confirm_password, {"password": " Тайна 1 "})

    assert "ok" in answer
    assert ("confirm_password", " Тайна 1 ") in login.calls


async def test_a_key_the_server_did_not_revoke_is_not_called_revoked(
    api, ask, hub, with_bot, session_factory
):
    """Неотозванный ключ выходом не считается, и учётная запись остаётся.

    Сеанс на серверах Telegram живёт дальше и продолжает читать переписку.
    Сотри мы учётные данные — человек считал бы себя вышедшим, а отозвать
    ключ было бы уже нечем: строки сеанса в настройках нет.
    """
    await put(
        session_factory,
        tg_account_row(
            api_hash_encrypted=encrypt_str("шифр"),
            session_blob_encrypted=encrypt_bytes("сессия".encode("utf-8")),
        ),
    )
    await hub.rs.reload()
    hub.login = UiLogin(LoginStep(payload={}, error=None))
    with_bot(log_out_refusal="сеть отвалилась")

    answer = await ask(api.settings.logout)

    assert "ok" not in answer
    assert hub.rs.has_tg_session is True


async def test_a_second_attempt_to_log_out_does_not_wipe_the_account_either(
    api, ask, hub, with_bot, session_factory
):
    """Второе нажатие «выйти» учётную запись тоже не стирает.

    Первый заход бота уже отвязал и обнулил, так что второй видит пустоту —
    и, приняв её за «отзывать было нечем», стёр бы настройки. Отзыва при этом
    не было ни разу: заслон, заведённый ради первого нажатия, обходился бы
    вторым.
    """
    await put(
        session_factory,
        tg_account_row(
            api_hash_encrypted=encrypt_str("шифр"),
            session_blob_encrypted=encrypt_bytes("сессия".encode("utf-8")),
        ),
    )
    await hub.rs.reload()
    hub.login = UiLogin(LoginStep(payload={}, error=None))
    with_bot(log_out_refusal="сеть отвалилась")
    await ask(api.settings.logout)

    answer = await ask(api.settings.logout)

    assert "ok" not in answer
    assert hub.rs.has_tg_session is True


async def test_logging_out_lets_the_bot_go(api, ask, hub, with_bot):
    """Выход из Telegram отвязывает бота прежде, чем стереть учётную запись.

    Бот держит ту же сессию: продолжи он работать, следующий его запрос ушёл
    бы с учётными данными, которых в настройках уже нет, и упал бы где-то
    посреди опроса каналов.
    """
    hub.login = UiLogin(LoginStep(payload={}, error=None))
    bot = with_bot()

    answer = await ask(api.settings.logout)

    assert "ok" in answer
    assert ("log_out_session",) in bot.calls
    assert hub.bot is None
