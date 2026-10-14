"""Следствия резюме — файла, путь к которому помнит окно.

Предмет отделён от анкеты: резюме не поле записи, а вложение на диске. Файл
мосту не выбирает никто: диалог был Qt'шный и ушёл вместе с каналом — путь
называет страница, а спрашивает его у человека диалог самого окна.
"""

import pytest

from backend.models import LlmConfigKind
from tests.client.conftest import WindowThatPicks
from tests.dbio import put
from tests.factories import CV_REQUIRED_PROFILE, llm_config_row
from tests.fakes.llm import CHAT, chat_json


async def test_the_path_to_the_resume_cannot_be_set_from_the_page(api):
    """Записать путь к резюме страница не может — только диалог самого окна.

    Заслон тот же, что у отправки файла собеседнику (`hr_chat._send_media`):
    поверхность моста pywebview собирает обходом полей и имена с подчёркиванием
    пропускает. У резюме он был снят, хотя цена здесь выше — записанный путь
    потом исполняется: «открыть резюме» отдаёт его `os.startfile` без всякого
    перечня расширений, в отличие от соседней дороги к файлам.
    """
    assert not hasattr(api.profile, "replace")


async def test_an_empty_path_is_refused(api, ask):
    """Пустой путь не сохраняют: подставлять в отклик будет нечего."""
    answer = await ask(api.profile._replace, {"path": "   "})

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Путь пустой"


async def test_a_replaced_resume_shows_up_in_the_profile(api, ask, tmp_path):
    """Заменённое резюме видно на экране анкеты, а не только в ответе.

    Путь помнят настройки, а показывает его анкета — это единственное место,
    где человек проверяет, какой файл уйдёт вместе с откликом.
    """
    resume = tmp_path / "новое.pdf"
    resume.write_bytes(b"%PDF-1.4 ")

    answer = await ask(api.profile._replace, {"path": str(resume)})
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
    await ask(api.profile._replace, {"path": str(resume)})

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
    assert answer["detail"] == "Резюме не выбрано"


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
    hub.window = WindowThatPicks([str(resume)])

    answer = await ask(api.profile.pick)

    assert answer["ok"]["exists"] is True
    shown = await ask(api.profile.get)
    assert shown["ok"]["cv_path"] == str(resume)


async def test_a_closed_dialog_changes_nothing(api, ask, hub):
    """Человек закрыл диалог, ничего не выбрав: прежнее резюме остаётся.

    Отказ здесь был бы неправдой — ничего не сломалось, человек передумал, — а
    пустой путь стёр бы прежний, и отклик ушёл бы без вложения.
    """
    hub.window = WindowThatPicks(None)

    answer = await ask(api.profile.pick)

    assert answer["ok"]["cancelled"] is True


@pytest.fixture
def resume_on_disk(tmp_path, api, ask):
    """Кладёт резюме на диск и запоминает путь — как это делает человек."""

    async def _put(body: str, name: str = "резюме.txt") -> str:
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        await ask(api.profile._replace, {"path": str(path)})
        return str(path)

    return _put


@pytest.fixture
async def chat_model(session_factory, runtime_settings):
    """Записывает выбранную чат-модель: разбор зовёт ту же, что и весь бот."""
    await put(session_factory, llm_config_row(LlmConfigKind.CHAT))
    await runtime_settings.reload()


async def test_parsing_a_resume_nobody_chose_is_refused(api, ask):
    """Пока файл не выбран, разбирать нечего, и работа не пускается."""
    answer = await ask(api.profile.parse_cv)

    assert answer["fail"] == "denied"
    assert answer["detail"] == "Резюме не выбрано"


async def test_parsing_without_a_chosen_model_is_refused(api, ask, resume_on_disk):
    """Без выбранной модели разбор не начинают: спрашивать некого.

    Отказ приходит до всякой работы. Пущенная, она вернулась бы вестью через
    минуту — и всю минуту человек ждал бы того, чего не будет.
    """
    await resume_on_disk("Иван Петров, разработчик.")

    answer = await ask(api.profile.parse_cv)

    assert answer["fail"] == "denied"
    assert "модель" in answer["detail"].lower()


async def test_a_file_that_cannot_be_read_is_explained_in_words(
    api, ask, told, resume_on_disk, chat_model
):
    """Нечитаемый файл называет, что с ним делать, а не «не получилось».

    Причины у отказа разные и чинятся по-разному: пропавший файл выбирают
    заново, `.doc` и запароленный PDF пересохраняют, скан не спасёт ничто.
    Скажи мост одно слово на все три — человек не узнал бы, что делать.
    """
    await resume_on_disk("не пдф вовсе", name="резюме.pdf")

    answer = await ask(api.profile.parse_cv)
    assert answer["ok"]["started"] is True

    said = await told()
    assert said["danger"] is True
    assert "пересохран" in said["message"].lower()


@pytest.fixture
async def model_says(chat_model, provider_says):
    """Записанная модель вместе с её ответом: разбору нужны обе половины."""

    def _answer(payload: dict) -> None:
        provider_says({CHAT: chat_json(payload)})

    return _answer


async def test_a_parsed_resume_fills_the_profile(
    api, ask, told, resume_on_disk, model_says
):
    """Разобранное резюме доезжает до анкеты, а не остаётся в ответе моста.

    В этом весь шаг: человек выбрал файл и получил заполненную анкету.
    Проверяется она с экрана анкеты, а не по ответу разбора — иначе зелёным
    прошёл бы мост, разобравший резюме и ничего не записавший.
    """
    await resume_on_disk("Иван Петров, разработчик. Python, SQL.")
    model_says({"profile": CV_REQUIRED_PROFILE})

    answer = await ask(api.profile.parse_cv)
    assert answer["ok"]["started"] is True

    said = await told()
    assert said["danger"] is False

    shown = await ask(api.profile.get)
    assert shown["ok"]["profile"]["first_name"] == CV_REQUIRED_PROFILE["first_name"]
