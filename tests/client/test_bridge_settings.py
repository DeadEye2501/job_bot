"""Следствия экрана настроек: что записано и что показано на экране.

Предмет — настройки приложения: куда ходить за моделью и с каким порогом
отбирать. Само хранение сторожит `tests/backend/test_runtime_settings_*.py`;
здесь смотрят на дорогу от формы до записи и обратно.
"""


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


async def test_an_unknown_setting_is_ignored_not_written(api, ask):
    """Незнакомая настройка не применяется и не попадает в список применённых.

    Список применённого окно показывает человеку. Попади туда имя, которого
    приложение не знает, человек считал бы настройку рабочей и ждал бы от неё
    поведения, которого нет.
    """
    answer = await ask(api.settings.save, {"app": {"придуманное": 1}})

    assert answer["ok"]["applied"] == []


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
