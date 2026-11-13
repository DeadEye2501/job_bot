"""Английское резюме уходит к откликам по-английски, основное — к остальным; нет нужного — другое."""

from sqlalchemy import update

from backend.applying.browser import via_browser
from backend.applying.email import via_email
from backend.applying.telegram import via_telegram
from backend.domain.apply_order import Way
from backend.models import Profile, Vacancy
from tests.backend.fixtures.applying import MAIL, PAGE, TG
from tests.dbio import put
from tests.factories import profile_row, resume_file


async def _speaks(kit, vacancy, language: str) -> None:
    async with kit.pipeline.session_factory() as session:
        async with session.begin():
            await session.execute(update(Vacancy).where(Vacancy.id == vacancy.id).values(language=language))


async def _english_link(kit, link: str) -> None:
    async with kit.pipeline.session_factory() as session:
        async with session.begin():
            await session.execute(update(Profile).values(resume_url_en=link))


async def test_an_english_vacancy_gets_the_english_file(mail_case, tmp_path):
    kit, vacancy, outbox = await mail_case()
    english = resume_file(tmp_path, "cv_en.pdf")
    await kit.pipeline.rs.set_cv_en_path(str(english))
    await _speaks(kit, vacancy, "English")

    assert await via_email(kit, vacancy.id, MAIL) == "applied"

    assert outbox[0].attachment == english


async def test_a_russian_vacancy_gets_the_main_file(mail_case, tmp_path):
    kit, vacancy, outbox = await mail_case()
    await kit.pipeline.rs.set_cv_en_path(str(resume_file(tmp_path, "cv_en.pdf")))
    await _speaks(kit, vacancy, "Русский")

    assert await via_email(kit, vacancy.id, MAIL) == "applied"

    assert outbox[0].attachment == kit.pipeline.cv_file()


async def test_a_missing_english_file_gives_way_to_the_main(mail_case, tmp_path):
    """Путь к английскому записан, а файла на диске нет: уходит основное, а не ничего."""
    kit, vacancy, outbox = await mail_case()
    await kit.pipeline.rs.set_cv_en_path(str(tmp_path / "gone.pdf"))
    await _speaks(kit, vacancy, "English")

    await via_email(kit, vacancy.id, MAIL)

    assert outbox[0].attachment == kit.pipeline.cv_file()


async def test_the_english_link_beats_the_main_file(mail_case):
    """Язык важнее формы: английская ссылка к отклику по-английски, а не основной файл."""
    kit, vacancy, outbox = await mail_case()
    await _english_link(kit, "https://example.com/cv-en")
    await _speaks(kit, vacancy, "English")

    await via_email(kit, vacancy.id, MAIL)

    assert outbox[0].attachment is None
    assert outbox[0].body.splitlines()[-1] == "https://example.com/cv-en"


async def test_without_the_main_resume_a_russian_vacancy_gets_the_english(mail_case, tmp_path):
    kit, vacancy, outbox = await mail_case(resume=False)
    english = resume_file(tmp_path, "cv_en.pdf")
    await kit.pipeline.rs.set_cv_en_path(str(english))
    await _speaks(kit, vacancy, "Русский")

    assert await via_email(kit, vacancy.id, MAIL) == "applied"

    assert outbox[0].attachment == english


async def test_a_telegram_letter_to_an_english_vacancy_carries_the_english_file(telegram_case, tmp_path):
    kit, vacancy, sent = await telegram_case()
    english = resume_file(tmp_path, "cv_en.pdf")
    await kit.pipeline.rs.set_cv_en_path(str(english))
    await _speaks(kit, vacancy, "English")

    assert await via_telegram(kit, vacancy.id, TG) == "applied"

    ((_, _, attachment),) = sent
    assert attachment == english


async def test_the_browser_attaches_the_english_file_to_an_english_vacancy(board, kit_with, tmp_path):
    site, vacancy = await board(language="English")

    async def attach(tools):
        await tools["browser_attach_resume"](selector="#cv")
        await tools["finish"](result="platform_closed")

    kit = await kit_with([attach])
    await kit.pipeline.rs.set_cv_path(str(resume_file(tmp_path, "cv.pdf")))
    english = resume_file(tmp_path, "cv_en.pdf")
    await kit.pipeline.rs.set_cv_en_path(str(english))

    await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))

    assert ("input_files", "#cv", str(english)) in (await kit.browser.page()).calls


async def test_a_telegram_letter_to_an_english_vacancy_carries_the_english_link(telegram_case):
    kit, vacancy, sent = await telegram_case()
    await _english_link(kit, "https://example.com/cv-en")
    await _speaks(kit, vacancy, "English")

    await via_telegram(kit, vacancy.id, TG)

    ((_, text, attachment),) = sent
    assert attachment is None and text.splitlines()[-1] == "https://example.com/cv-en"


async def _attached_by_browser(board, kit_with, language: str, set_files) -> list:
    """Что агент приложил к форме вакансии на `language`; `set_files(kit)` раскладывает резюме."""
    site, vacancy = await board(language=language)
    answers = []

    async def attach(tools):
        answers.append(await tools["browser_attach_resume"](selector="#cv"))
        await tools["finish"](result="platform_closed")

    kit = await kit_with([attach])
    await set_files(kit)
    await via_browser(kit, vacancy.id, Way("aggregator", PAGE, site.id))
    return answers, (await kit.browser.page()).calls


async def test_the_browser_does_not_attach_the_main_file_to_an_english_vacancy(board, kit_with, tmp_path):
    """Английское резюме одной ссылкой: русский файл к английской вакансии не
    прикладывается — агенту отвечают, что файла нет."""
    async def files(kit):
        await put(kit.pipeline.session_factory, profile_row(resume_url_en="https://example.com/cv-en"))
        await kit.pipeline.rs.set_cv_path(str(resume_file(tmp_path, "cv.pdf")))

    answers, calls = await _attached_by_browser(board, kit_with, "English", files)

    assert answers == ["нет файла резюме"] and calls == []


async def test_the_browser_attaches_the_english_file_when_the_main_has_none(board, kit_with, tmp_path):
    """Основное резюме одной ссылкой: к русской вакансии идёт английский файл —
    английское резюме к русской вакансии уместно."""
    english = resume_file(tmp_path, "cv_en.pdf")

    async def files(kit):
        await put(kit.pipeline.session_factory, profile_row(resume_url="https://hh.ru/resume/ru"))
        await kit.pipeline.rs.set_cv_en_path(str(english))

    _, calls = await _attached_by_browser(board, kit_with, "Русский", files)

    assert ("input_files", "#cv", str(english)) in calls


async def test_the_agent_sees_the_link_of_the_resume_that_goes(mail_case):
    kit, vacancy, _ = await mail_case(resume="https://hh.ru/resume/ru")
    await _english_link(kit, "https://example.com/cv-en")

    await _speaks(kit, vacancy, "English")
    english = await kit.read(lambda session: kit.vacancy_profile_text(session, vacancy.id))
    await _speaks(kit, vacancy, "Русский")
    russian = await kit.read(lambda session: kit.vacancy_profile_text(session, vacancy.id))

    assert "Ссылка на резюме: https://example.com/cv-en" in english
    assert "Ссылка на резюме: https://hh.ru/resume/ru" in russian
