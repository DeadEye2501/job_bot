"""Следствия слотов резюме — файла, путь к которому помнит окно.

Предмет отделён от анкеты: резюме не поле записи, а вложение на диске. Оба
окна умеют его выбирать, и оба здесь: мастер первого запуска спрашивает файл
теми же руками, что и основное окно потом.
"""

import json


async def test_choosing_a_file_answers_the_call_itself(
    main_api, chosen_file, tmp_path
):
    """Выбор файла отвечает возвратом вызова, а не сигналом.

    Это один из двух слотов моста, устроенных так: окно ждёт ответа прямо на
    месте, потому что следующий шаг — показать выбранное имя в форме, и
    показывать его надо сразу, а не когда-нибудь потом.
    """
    resume = tmp_path / "резюме.pdf"
    resume.write_bytes(b"%PDF-1.4 ")
    chosen_file(str(resume))

    answer = json.loads(main_api.pick_cv_file_main())

    assert answer["ok"] is True
    assert answer["path"] == str(resume)
    assert answer["name"] == "резюме.pdf"


async def test_a_cancelled_choice_is_told_apart_from_a_failure(
    main_api, chosen_file
):
    """Передумавшего отличают от поломки отдельным словом.

    Закрытое окно выбора — обычный отказ от намерения, и окну надо просто
    ничего не менять. Приди сюда общая ошибка, человек увидел бы сообщение о
    поломке всякий раз, когда просто передумал.
    """
    chosen_file("")

    answer = json.loads(main_api.pick_cv_file_main())

    assert answer["ok"] is False
    assert answer["error"] == "cancelled"


async def test_an_empty_path_is_refused(main_api, watch):
    """Пустой путь не сохраняют: подставлять в отклик будет нечего."""
    caught = watch(main_api.cv_replace_done)

    main_api.replace_cv(json.dumps({"path": "   "}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Путь пустой."


async def test_a_replaced_resume_shows_up_in_the_profile(
    main_api, watch, tmp_path
):
    """Заменённое резюме видно на экране анкеты, а не только в ответе.

    Путь помнят настройки, а показывает его анкета — это единственное место,
    где человек проверяет, какой файл уйдёт вместе с откликом.
    """
    resume = tmp_path / "новое.pdf"
    resume.write_bytes(b"%PDF-1.4 ")
    replaced = watch(main_api.cv_replace_done)
    shown = watch(main_api.profile_changed)

    main_api.replace_cv(json.dumps({"path": str(resume)}))
    answer = await replaced.next()
    assert answer["ok"] is True
    assert answer["exists"] is True

    main_api.request_profile()
    assert (await shown.next())["cv_path"] == str(resume)


async def test_a_resume_that_went_missing_is_reported_as_missing(
    main_api, watch, tmp_path
):
    """Про пропавший с диска файл говорят прямо, а не молчат.

    Путь помнится в настройках, а файл человек мог переложить или удалить.
    Промолчи мост — пропажа вскрылась бы только на отправке отклика, когда
    прикладывать уже нечего.
    """
    resume = tmp_path / "было.pdf"
    resume.write_bytes(b"%PDF-1.4 ")
    replaced = watch(main_api.cv_replace_done)
    main_api.replace_cv(json.dumps({"path": str(resume)}))
    await replaced.next()

    resume.unlink()
    shown = watch(main_api.profile_changed)

    main_api.request_profile()

    assert (await shown.next())["cv_meta"]["exists"] is False


async def test_the_wizard_asks_for_the_file_the_same_way(wizard_api, chosen_file, tmp_path):
    """Мастер первого запуска спрашивает файл тем же способом.

    Оба окна зовут один и тот же диалог и отвечают возвратом вызова: мастер
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
    wizard_api, watch, main_api, tmp_path
):
    """Приложенное в мастере резюме видно основному окну.

    Мастер и основное окно — разные объекты моста, и настройки для них общие
    только через записанное. Не доедь путь, человек прошёл бы мастер и увидел
    в анкете пустое поле резюме.
    """
    resume = tmp_path / "из мастера.pdf"
    resume.write_bytes(b"%PDF-1.4 ")
    saved = watch(wizard_api.cv_save_done)
    shown = watch(main_api.profile_changed)

    wizard_api.cv_save(json.dumps({"mode": "attach", "path": str(resume)}))
    assert (await saved.next())["ok"] is True

    main_api.request_profile()
    assert (await shown.next())["cv_path"] == str(resume)
