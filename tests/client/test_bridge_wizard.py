"""Следствия первого запуска: с какого шага он продолжается и чем кончается.

Предмет — сам порядок первого запуска. Шаги, которые мастер делает теми же
доменами, что и основное окно — вход в Telegram, проверка модели, её запись,
выбор резюме, — сторожатся со своими предметами: тела у них общие, и проверять
их дважды незачем.
"""

import json

from backend.crypto import encrypt_str
from backend.models import LlmConfigKind
from backend.runtime_settings import RuntimeSettings
from tests.dbio import put
from tests.factories import llm_config_row, tg_account_row


async def test_an_empty_setup_has_no_steps_behind_it(api, ask):
    """На пустой установке пройденных шагов нет ни одного.

    По этому списку мастер решает, с какого шага открыться. Соври он про
    пройденное — человек попал бы сразу на последний шаг, не введя ни
    учётной записи, ни модели.
    """
    answer = await ask(api.wizard.state)

    assert answer["ok"]["completed"] == []
    assert answer["ok"]["wizard_completed"] is False


async def test_the_cloud_password_never_leaves_the_bridge(
    api, ask, runtime_settings, session_factory
):
    """Облачный пароль Telegram в снимок мастера не попадает.

    Читать его на странице нечему: мастер спрашивает пароль формой и шлёт
    введённое обратно, а не показывает сохранённое. Уехавший же он лежит в
    памяти окна всю его жизнь — вместе со всем, что окно про себя помнит.
    """
    await put(
        session_factory,
        tg_account_row(
            api_hash_encrypted=encrypt_str("ш"),
            password_encrypted=encrypt_str("облачный"),
        ),
    )
    await runtime_settings.reload()
    # Пароль и правда лежит в настройках: без этой строки сторож был бы зелен
    # оттого, что отдавать было нечего.
    assert runtime_settings.tg.password == "облачный"

    answer = await ask(api.wizard.state)

    # Ищем сам секрет по всему ответу, а не имя ключа: уехавший под другим
    # именем — та же утечка, а имён у него может быть сколько угодно.
    assert "облачный" not in json.dumps(answer, ensure_ascii=False)


async def test_credentials_without_a_session_do_not_count_as_a_step(
    api, ask, runtime_settings, session_factory
):
    """Введённые учётные данные без сохранённой сессии шагом не считаются.

    Данные вводят на первом шаге, а сессия появляется только после кода
    подтверждения. Засчитай мастер шаг раньше — человек ушёл бы дальше, а
    бот при запуске не подключился бы, и причина осталась бы в прошлом шаге.

    Хэш записываем настоящим: без него запись учётной записи не читается
    вовсе, и шаг не засчитался бы по другой причине — тест был бы зелен, не
    проверив ничего.
    """
    await put(
        session_factory,
        tg_account_row(
            api_hash_encrypted=encrypt_str("ш"), session_blob_encrypted=None
        ),
    )
    await runtime_settings.reload()

    answer = await ask(api.wizard.state)

    assert answer["ok"]["completed"] == []
    assert answer["ok"]["tg"]["api_hash"] == "ш"


async def test_a_saved_model_counts_as_a_step(
    api, ask, runtime_settings, session_factory
):
    """Сохранённая чат-модель засчитывается пройденным шагом и приезжает назад.

    Мастер продолжают в другой день и с другого запуска; шаги, сделанные
    вчера, переспрашивать незачем. Само записанное едет вместе со счётом:
    придя пустым, оно заставило бы человека перепечатать поверх того, что уже
    лежит в базе, — а шаг при этом числился бы пройденным.
    """
    await put(session_factory, llm_config_row(LlmConfigKind.CHAT))
    await runtime_settings.reload()

    answer = await ask(api.wizard.state)

    assert 2 in answer["ok"]["completed"]
    # С литералом фабрики, а не с настройками: обе стороны читали бы
    # один объект, и мост, отдающий вместо записанного что угодно из тех же
    # настроек, прошёл бы зелёным.
    assert answer["ok"]["chat"]["model"] == "qwen"


async def test_a_saved_embedding_model_counts_as_its_own_step(
    api, ask, runtime_settings, session_factory
):
    """Модель векторов засчитывается своим шагом, а не шагом чат-модели.

    Шага два, и записываются они порознь. Спутай мастер их номера — человек,
    вернувшийся к прерванной установке, переспрашивал бы уже введённое и
    проскакивал невведённое.

    Красной фазы у этого сторожа не было: дописан по находке ревью — шаги 3 и 4
    можно было снести, и прогон остался бы зелёным.
    """
    await put(session_factory, llm_config_row(LlmConfigKind.EMBED))
    await runtime_settings.reload()

    answer = await ask(api.wizard.state)

    assert answer["ok"]["completed"] == [3]


async def test_a_chosen_resume_counts_as_the_last_step(api, ask, tmp_path):
    """Выбранное резюме засчитывается последним шагом мастера.

    Шаг резюме — единственный, который засчитывается по записи вне мастера:
    путь кладёт домен анкеты. Не смотри мастер туда, человек, выбравший файл,
    возвращался бы на тот же шаг после каждого перезапуска.

    Красной фазы не было — дописан по той же находке.
    """
    resume = tmp_path / "уже выбрано.pdf"
    resume.write_bytes(b"%PDF-1.4 ")
    await ask(api.profile.replace, {"path": str(resume)})

    answer = await ask(api.wizard.state)

    assert 4 in answer["ok"]["completed"]


async def test_skipping_the_resume_forgets_the_chosen_file(api, ask, tmp_path):
    """Пропуск резюме стирает выбранный до него файл, а не оставляет его.

    Человек выбирает файл, передумывает и жмёт «пропустить». Останься путь
    записанным — отклики уходили бы с вложением, от которого человек только
    что отказался, и увидел бы он это лишь в отправленном письме.
    """
    resume = tmp_path / "передумал.pdf"
    resume.write_bytes(b"%PDF-1.4 ")
    await ask(api.profile.replace, {"path": str(resume)})

    answer = await ask(api.wizard.skip_cv)

    assert "ok" in answer
    assert (await ask(api.profile.get))["ok"]["cv_path"] == ""
    assert (await ask(api.wizard.state))["ok"]["cv_path"] == ""


async def test_the_setup_is_marked_done_only_when_it_is_completed(
    api, ask, session_factory, hub, growing_window
):
    """Установка помечается завершённой ровно тогда, когда её завершают.

    Отметка решает, что покажет следующий запуск. Поставь её мастер раньше —
    брошенная посреди установка открылась бы в ненастроенном приложении; не
    поставь вовсе — мастер открывался бы каждый раз заново поверх настроенного.
    """
    hub.window = growing_window
    assert (await ask(api.wizard.state))["ok"]["wizard_completed"] is False

    answer = await ask(api.wizard.complete)

    assert "ok" in answer
    assert (await RuntimeSettings.load(session_factory)).wizard_completed is True


async def test_the_end_of_the_setup_leaves_the_window_alone(api, ask, hub, growing_window):
    """Конец установки окна не трогает.

    После него человек читает последний экран мастера — что сделать дальше, —
    и читает он его в окне мастера. Вырасти окно здесь, страница раздалась бы
    под ним прямо на глазах, до того как он дочитал.
    """
    hub.window = growing_window

    await ask(api.wizard.complete)

    assert growing_window.done == []


async def test_the_window_grows_when_the_app_is_opened(api, ask, hub, growing_window):
    """Окно растёт по переходу в приложение, а не раньше.

    Окно открывалось под мастера — меньшим и нерастягиваемым. Не вырасти оно
    здесь, человек увидел бы приложение в окне мастера и не смог бы даже
    потянуть за край: разметка сплющена, а растить нечем — до следующего
    запуска.
    """
    hub.window = growing_window

    await ask(api.wizard.enter_main_app)

    assert ("выросло", 900, 660) in growing_window.done


async def test_a_finished_setup_does_not_wake_a_bot_it_cannot_build(
    api, ask, hub, growing_window
):
    """Конец мастера на недонастроенном приложении бота не поднимает.

    Мастер доходит до конца и с пропущенными шагами — их пропускают, чтобы
    посмотреть приложение. Собери мост бота на пустых моделях, тот отказал бы
    броском, и человек прочитал бы в журнале «бот упал» ровно там, где всё
    идёт по плану.

    Красной фазы не было: сторож дописан вместе с заслоном, найденным ревью, и
    доверие заслужит итоговым проходом.
    """
    hub.window = growing_window

    await ask(api.wizard.complete)

    assert hub.bot is None
    assert hub.bot_task is None
