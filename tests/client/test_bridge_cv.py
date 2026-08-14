"""Следствия резюме — файла, путь к которому помнит окно.

Предмет отделён от анкеты: резюме не поле записи, а вложение на диске. Файл
мосту не выбирает никто: диалог был Qt'шный и ушёл вместе с каналом — путь
называет страница, а спрашивает его у человека диалог самого окна.
"""


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


async def test_the_window_asks_the_person_for_a_file(api, ask, hub, tmp_path):
    """Файл выбирают диалогом самого окна, а не набором пути руками.

    Со страницы этот диалог не позвать: он у окна, а не у моста, — и мост
    здесь единственный, кто до него дотягивается.
    """
    resume = tmp_path / "выбранное.pdf"
    resume.write_bytes(b"%PDF-1.4 ")
    hub.window = _WindowThatPicks([str(resume)])

    answer = await ask(api.profile.pick)

    assert answer["ok"]["exists"] is True
    shown = await ask(api.profile.get)
    assert shown["ok"]["cv_path"] == str(resume)


async def test_a_closed_dialog_changes_nothing(api, ask, hub):
    """Человек закрыл диалог, ничего не выбрав: прежнее резюме остаётся.

    Отказ здесь был бы неправдой — ничего не сломалось, человек передумал, — а
    пустой путь стёр бы прежний, и отклик ушёл бы без вложения.
    """
    hub.window = _WindowThatPicks(None)

    answer = await ask(api.profile.pick)

    assert answer["ok"]["cancelled"] is True


class _WindowThatPicks:
    """Окно, которое отвечает на диалог заранее назначенным выбором."""

    def __init__(self, chosen) -> None:
        self.chosen = chosen
        self.asked = []

    def create_file_dialog(self, *args, **kwargs):
        self.asked.append(kwargs)
        return self.chosen
