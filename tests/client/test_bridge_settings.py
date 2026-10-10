"""Следствия экрана настроек: что записано и что показано на экране.

Предмет — настройки приложения: куда ходить за моделью и с каким порогом
отбирать. Само хранение сторожит `tests/backend/test_runtime_settings_*.py`;
здесь смотрят на дорогу от формы до записи и обратно.
"""

from backend.agent.availability import NO_DRIVER
from backend.models import AppSetting


async def test_an_empty_model_name_is_refused_before_saving(api, ask):
    """Пустое имя модели отбивают до записи в настройки.

    С пустым именем каждый запрос к модели вернёт отказ, а выглядеть это
    будет как поломка разбора вакансий. Сохранись оно — искать причину
    пришлось бы в журнале, а не в форме, где её видно сразу.

    Отказ называет поставщика: экран настроек правит обоих сразу, и без
    имени человек не знает, в каком из двух полей стёрлось.
    """
    answer = await ask(
        api.settings.save,
        {"chat": {"base_url": "http://localhost:1234", "model": "  "}},
    )

    assert answer["fail"] == "denied"
    assert answer["detail"] == "chat: Заполните base_url и модель."


async def test_saved_settings_come_back_on_the_next_request(api, ask):
    """Сохранённое видно при следующем открытии экрана настроек.

    Настройки читают, чтобы проверить, куда именно уходят запросы к модели.
    Не вернись записанное — человек правил бы форму второй раз поверх уже
    сохранённого.
    """
    saved = await ask(
        api.settings.save,
        {
            "chat": {
                "base_url": "http://localhost:1234/",
                "api_key": "",
                "model": "qwen",
            },
            "app": {"scoring_threshold": 7},
        },
    )
    assert "ok" in saved

    answer = await ask(api.settings.get)
    assert answer["ok"]["chat"]["model"] == "qwen"
    assert answer["ok"]["pipeline"]["scoring_threshold"] == 7


async def test_an_unknown_setting_is_ignored_not_written(api, ask, session_factory):
    """Незнакомая настройка не доезжает до базы и не числится применённой.

    Перечень позволенного стоит затем, чтобы опечатка в имени не легла в
    настройки своим ключом и не осталась там навсегда, никем не читаемая.
    Список применённого — вторая половина того же: попади туда незнакомое имя,
    человек считал бы настройку рабочей и ждал бы от неё поведения, которого
    нет.

    Записанное спрашиваем у базы, а не у ответа моста: ответ про запись только
    рассказывает, а сторожим мы саму запись.
    """
    answer = await ask(api.settings.save, {"app": {"придуманное": 1}})

    assert answer["ok"]["applied"] == []
    async with session_factory() as session:
        assert await session.get(AppSetting, "придуманное") is None


async def test_saving_a_provider_without_an_address_is_refused(api, ask):
    """Пустой адрес поставщика не сохраняют молча.

    Записанная пустота стирает поставщика целиком: экран показывает пустые
    поля, будто их никто не заполнял, а разбор вакансий перестаёт работать —
    и связать одно с другим человеку нечем.
    """
    answer = await ask(
        api.settings.save,
        {"chat": {"base_url": "", "api_key": "", "model": "qwen"}},
    )

    assert answer["fail"] == "denied"
    assert "Заполните base_url и модель." in answer["detail"]


async def test_the_aggregator_settings_come_back_after_saving(api, ask):
    await ask(api.settings.save, {"app": {
        "aggregator_backfill_limit": 30, "show_browser": True, "letter_writer": "agent",
    }})

    snapshot = (await ask(api.settings.get))["ok"]["aggregators"]

    saved = ("aggregator_backfill_limit", "show_browser", "letter_writer")
    assert {key: snapshot[key] for key in saved} == {
        "aggregator_backfill_limit": 30, "show_browser": True, "letter_writer": "agent",
    }


async def test_mail_settings_come_back_with_the_password(api, ask):
    """Пароль окну отдаётся, как ключи моделей и `api_hash`: подключённая почта
    открывается с паролем точками, и глазом его можно показать."""
    saved = await ask(api.settings.save_mail, {"address": "me@gmail.com", "password": "Kx9-mail"})

    answer = (await ask(api.settings.mail))["ok"]

    assert "ok" in saved
    assert answer == {"address": "me@gmail.com", "password": "Kx9-mail", "smtp_host": "smtp.gmail.com",
                      "smtp_port": 465, "server_by_address": True}


async def test_a_server_typed_by_hand_is_not_by_address(api, ask):
    """Окно держит поля сервера, пока сервер не подставлен по адресу: вписанный руками
    сервер незнакомой почты иначе было бы негде поправить."""
    await ask(api.settings.save_mail, {"address": "me@company.test", "password": "x",
                                       "smtp_host": "smtp.company.test", "smtp_port": 587})

    answer = (await ask(api.settings.mail))["ok"]

    assert (answer["smtp_host"], answer["server_by_address"]) == ("smtp.company.test", False)


async def test_the_aggregator_snapshot_names_the_browser_and_what_locks_the_agent(
    api, ask, monkeypatch
):
    from adapters.browser import InstalledBrowser

    monkeypatch.setattr("client.bridge.settings.find_browser",
                        lambda: InstalledBrowser("Opera", None, None))
    aggregators = (await ask(api.settings.get))["ok"]["aggregators"]

    assert aggregators["browser"] == "Opera" and aggregators["lock"] == NO_DRIVER
