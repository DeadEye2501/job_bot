"""Следствия слотов настроек: что записано и что показано на экране.

Предмет — настройки приложения: куда ходить за моделью и с каким порогом
отбирать. Само хранение сторожит `tests/backend/test_runtime_settings_*.py`;
здесь смотрят на дорогу от формы до записи и обратно.
"""

import json


async def test_an_empty_model_name_is_refused_before_saving(main_api, watch):
    """Пустое имя модели отбивают до записи в настройки.

    С пустым именем каждый запрос к модели вернёт отказ, а выглядеть это
    будет как поломка разбора вакансий. Сохранись оно — искать причину
    пришлось бы в журнале, а не в форме, где её видно сразу.

    Отказ называет поставщика: экран настроек правит обоих сразу, и без
    имени человек не знает, в каком из двух полей стёрлось.
    """
    caught = watch(main_api.settings_save_done)

    main_api.save_settings(
        json.dumps({"chat": {"base_url": "http://localhost:1234", "model": "  "}})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "chat: Заполните base_url и модель."


async def test_saved_settings_come_back_on_the_next_request(main_api, watch):
    """Сохранённое видно при следующем открытии экрана настроек.

    Настройки читают, чтобы проверить, куда именно уходят запросы к модели.
    Не вернись записанное — человек правил бы форму второй раз поверх уже
    сохранённого.
    """
    saved = watch(main_api.settings_save_done)
    shown = watch(main_api.system_settings_loaded)

    main_api.save_settings(
        json.dumps(
            {
                "chat": {
                    "base_url": "http://localhost:1234/",
                    "api_key": "",
                    "model": "qwen",
                },
                "app": {"scoring_threshold": 7},
            }
        )
    )
    assert (await saved.next())["ok"] is True

    main_api.request_system_settings()
    answer = await shown.next()
    assert answer["chat"]["model"] == "qwen"
    assert answer["pipeline"]["scoring_threshold"] == 7


async def test_an_unknown_setting_is_ignored_not_written(main_api, watch):
    """Незнакомая настройка не применяется и не попадает в список применённых.

    Список применённого окно показывает человеку. Попади туда имя, которого
    приложение не знает, человек считал бы настройку рабочей и ждал бы от неё
    поведения, которого нет.
    """
    caught = watch(main_api.settings_save_done)

    main_api.save_settings(json.dumps({"app": {"придуманное": 1}}))

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["applied"] == []


async def test_saving_a_provider_without_an_address_is_refused(main_api, watch):
    """Пустой адрес поставщика не сохраняют молча.

    Записанная пустота стирает поставщика целиком: экран показывает пустые
    поля, будто их никто не заполнял, а разбор вакансий перестаёт работать —
    и связать одно с другим человеку нечем.
    """
    caught = watch(main_api.settings_save_done)

    main_api.save_settings(
        json.dumps({"chat": {"base_url": "", "api_key": "", "model": "qwen"}})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert "Заполните base_url и модель." in answer["error"]
