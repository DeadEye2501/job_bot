"""Следствия слотов резюме — файла, путь к которому помнит окно.

Предмет отделён от анкеты: резюме не поле записи, а вложение на диске. Выбирать
файл умеет только мастер первого запуска: у основного окна диалог был Qt'шный и
ушёл вместе с переездом домена — путь туда называет страница.
"""

import json


async def test_an_empty_path_is_refused(api, ask):
    """Пустой путь не сохраняют: подставлять в отклик будет нечего."""
    answer = await ask(api.profile.replace, {"path": "   "})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Путь пустой."


async def test_a_replaced_resume_shows_up_in_the_profile(api, ask, tmp_path):
    """Заменённое резюме видно на экране анкеты, а не только в ответе.

    Путь помнят настройки, а показывает его анкета — это единственное место,
    где человек проверяет, какой файл уйдёт вместе с откликом.
    """
    resume = tmp_path / "новое.pdf"
    resume.write_bytes(b"%PDF-1.4 ")

    answer = await ask(api.profile.replace, {"path": str(resume)})
    assert answer["ok"]["exists"] is True

    shown = await ask(api.profile.get)
    assert shown["ok"]["cv_path"] == str(resume)


async def test_a_resume_that_went_missing_is_reported_as_missing(api, ask, tmp_path):
    """Про пропавший с диска файл говорят прямо, а не молчат.

    Путь помнится в настройках, а файл человек мог переложить или удалить.
    Промолчи мост — пропажа вскрылась бы только на отправке отклика, когда
    прикладывать уже нечего.
    """
    resume = tmp_path / "было.pdf"
    resume.write_bytes(b"%PDF-1.4 ")
    await ask(api.profile.replace, {"path": str(resume)})

    resume.unlink()

    shown = await ask(api.profile.get)

    assert shown["ok"]["cv_meta"]["exists"] is False


async def test_the_wizard_asks_for_the_file_itself(
    wizard_api, chosen_file, tmp_path
):
    """Мастер первого запуска спрашивает файл сам, диалогом.

    Диалог остался только у него и отвечает возвратом вызова: мастер
    показывает выбранное имя на своём шаге, и ждать его сигналом там нечем —
    шага впереди ещё нет.
    """
    resume = tmp_path / "первое.pdf"
    resume.write_bytes(b"%PDF-1.4 ")
    chosen_file(str(resume))

    answer = json.loads(wizard_api.pick_cv_file())

    assert answer["ok"] is True
    assert answer["name"] == "первое.pdf"


async def test_the_wizard_lets_the_resume_be_skipped(wizard_api, watch):
    """Резюме можно не прикладывать вовсе, и мастер это принимает.

    Отклик без файла всё равно уйдёт — письмо важнее вложения. Отбей мастер
    пропуск, человек застрял бы на первом запуске, не имея файла под рукой.
    """
    caught = watch(wizard_api.cv_save_done)

    wizard_api.cv_save(json.dumps({"mode": "skip"}))

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["mode"] == "skip"


async def test_the_wizard_refuses_to_attach_nothing(wizard_api, watch):
    """Приложить нечего — так и говорят, вместо того чтобы записать пустоту.

    Пустой путь дошёл бы до настроек и всплыл бы позже: отклик ушёл бы без
    обещанного вложения, и заметить это было бы уже нельзя.
    """
    caught = watch(wizard_api.cv_save_done)

    wizard_api.cv_save(json.dumps({"mode": "attach", "path": "  "}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Сначала выберите файл резюме."


async def test_an_attached_resume_is_remembered_for_the_main_window(
    wizard_api, watch, api, ask, tmp_path
):
    """Приложенное в мастере резюме видно основному окну.

    Мастер и основное окно — разные объекты моста, и настройки для них общие
    только через записанное. Не доедь путь, человек прошёл бы мастер и увидел
    в анкете пустое поле резюме.
    """
    resume = tmp_path / "из мастера.pdf"
    resume.write_bytes(b"%PDF-1.4 ")
    saved = watch(wizard_api.cv_save_done)

    wizard_api.cv_save(json.dumps({"mode": "attach", "path": str(resume)}))
    assert (await saved.next())["ok"] is True

    shown = await ask(api.profile.get)
    assert shown["ok"]["cv_path"] == str(resume)


async def test_a_resume_nobody_chose_is_not_handed_to_the_system(api, ask):
    """Открывать нечего — окну говорят словами, а не молчанием.

    Кнопка «Открыть» стоит на экране и до того, как резюме выбрано; молчание в
    ответ человек читает как поломку приложения.
    """
    answer = await ask(api.profile.open)

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Резюме не выбрано."


async def test_a_chosen_resume_goes_to_the_system_by_its_full_path(
    api, ask, runtime_settings, monkeypatch, tmp_path
):
    """Выбранное резюме уезжает системе полным путём, а не тем, что записано.

    Настройки помнят путь таким, каким его назвал человек, — он бывает и
    относительным. Система же открывает от своего рабочего каталога, а он у
    собранного приложения чужой.
    """
    (tmp_path / "резюме.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.chdir(tmp_path)
    await runtime_settings.set_app("cv_path", "резюме.pdf")
    handed: list[str] = []
    monkeypatch.setattr(
        "client.bridge.cv.open_in_system", lambda path: handed.append(path) or True
    )

    answer = await ask(api.profile.open)

    assert handed == [str((tmp_path / "резюме.pdf").resolve())]
    assert answer["ok"]["path"] == "резюме.pdf"


async def test_a_resume_the_system_would_not_open_is_not_called_opened(
    api, ask, runtime_settings, monkeypatch
):
    """Не открывшееся резюме названо отказом, а не успехом.

    Экран анкеты в этот же миг показывает, что файла по пути нет; ответь мы
    «открыли», человек читал бы на одном экране два противоположных
    утверждения.
    """
    await runtime_settings.set_app("cv_path", "C:/нет/такого.pdf")
    monkeypatch.setattr("client.bridge.cv.open_in_system", lambda path: False)

    answer = await ask(api.profile.open)

    assert answer["fail"] == "denied"
    assert answer["path"] == "C:/нет/такого.pdf"


async def test_a_cancelled_choice_is_told_apart_from_a_failure(
    wizard_api, chosen_file
):
    """Передумавшего отличают от поломки отдельным словом.

    Закрытое окно выбора — обычный отказ от намерения, и окну надо просто
    ничего не менять. Приди сюда общая ошибка, человек увидел бы сообщение о
    поломке всякий раз, когда просто передумал.

    Сторож переехал с поверхности основного окна на мастера: диалог остался
    только у него, а различение живо и там.
    """
    chosen_file("")

    answer = json.loads(wizard_api.pick_cv_file())

    assert answer["ok"] is False
    assert answer["error"] == "cancelled"
