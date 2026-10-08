"""Следствия зова о языках вакансии.

Заслон на выдуманное обоснование живёт здесь, а не общим у трёх зовов: приметы
у него языковые — уровень CEFR и ежедневные созвоны, — и другим двум ловить
ими нечего.

Пойманная выдумка переворачивает отказ в «подходит»: пропустить лишнюю
вакансию на ручной просмотр дешевле, чем потерять настоящую.

Эти же проверки — единственный сторож `backend/llm/hallucination.py` в части
выдумки: снаружи она видна только перевёрнутым вердиктом.
"""

from functools import partial

from backend.llm.candidate import CandidateLanguage, CandidateProfile
from backend.llm.fit_languages import validate_language_fit
from tests.backend.fixtures.fit import asked, verdict
from tests.factories import parsed_vacancy
from tests.fakes.llm import CHAT, fit_answer, messages_of, provider

_asked = partial(asked, validate_language_fit)
_check = partial(verdict, validate_language_fit)


async def test_the_question_about_languages_gets_no_parsed_fields():
    """Зову о языках разобранных полей не дают — только текст объявления.

    Стек — чужой критерий, и попав в наставление, он становится поводом для
    отказа не по своему вопросу: прежде один зов видел всё сразу и путал
    критерии между собой.
    """
    client = provider({CHAT: fit_answer("fit", "языковых требований нет")})

    await _check(
        client,
        raw_text="нужен английский",
        parsed=parsed_vacancy(stack_required=["Python"]),
    )

    user = messages_of(client.sent[0])["user"]
    assert "нужен английский" in user
    assert "stack_required" not in user
    assert "Python" not in user


async def test_a_made_up_reason_for_rejection_flips_the_verdict():
    """Выдуманное обоснование отказа переворачивает вердикт в «подходит».

    Модель сослалась на требование к языку, которого в объявлении нет.
    Пропустить такую вакансию на ручной просмотр дешевле, чем потерять
    настоящую из-за фантазии модели.
    """
    client = provider(
        {CHAT: fit_answer("reject", "вакансия подразумевает английский язык")}
    )
    profile = CandidateProfile(
        languages=[CandidateLanguage(name="Английский", level="A2")]
    )

    got = await _check(
        client, raw_text="Ищем питониста в Тбилиси, оформление по договору", profile=profile
    )

    assert got.verdict == "fit"
    assert got.reason is None


async def test_a_made_up_reason_is_caught_without_any_profile_data():
    """Выдумка ловится и без сведений о кандидате — по общим приметам.

    Приметы двух родов: общие, не зависящие от профиля, и построенные по
    языкам кандидата. Профиль здесь пуст нарочно: вторые не построятся
    вовсе, и сработать могут только первые — уровень языка, названный в
    обосновании, но отсутствующий в объявлении.
    """
    client = provider({CHAT: fit_answer("reject", "требуется уровень B2")})

    got = await _check(
        client,
        raw_text="Ищем питониста в бэкенд, оформление по договору",
        profile=CandidateProfile(),
    )

    assert got.verdict == "fit"
    assert got.reason is None


async def test_a_level_named_in_the_post_is_not_taken_for_a_made_up_one():
    """Уровень, названный в объявлении, выдумкой не считается."""
    client = provider({CHAT: fit_answer("reject", "требуется уровень B2")})

    got = await _check(
        client,
        raw_text="Ищем питониста, английский B2 обязателен",
        profile=CandidateProfile(),
    )

    assert got.verdict == "reject"
    assert got.reason == "требуется уровень B2"


async def test_a_reason_backed_by_the_post_survives():
    """Обоснование, подкреплённое текстом объявления, остаётся как есть."""
    client = provider(
        {CHAT: fit_answer("reject", "вакансия подразумевает английский язык")}
    )
    profile = CandidateProfile(
        languages=[CandidateLanguage(name="Английский", level="A2")]
    )

    got = await _check(
        client,
        raw_text="Ищем питониста. Обязателен английский язык уровня C1.",
        profile=profile,
    )

    assert got.verdict == "reject"
    assert got.reason == "вакансия подразумевает английский язык"


async def test_a_fitting_verdict_is_never_second_guessed():
    """Вердикт «подходит» на выдуманность не проверяют.

    Проверка нужна там, где вакансия отбрасывается: пропущенная лишняя
    вакансия видна пользователю, а отброшенная — нет.
    """
    client = provider(
        {CHAT: fit_answer("fit", "вакансия подразумевает английский язык")}
    )
    profile = CandidateProfile(
        languages=[CandidateLanguage(name="Английский", level="A2")]
    )

    got = await _check(client, raw_text="Ищем питониста.", profile=profile)

    assert got.verdict == "fit"
    assert got.reason == "вакансия подразумевает английский язык"


async def test_fluency_without_a_language_does_not_confirm_a_language_demand():
    """«Свободный график» подтверждением требования к языку не считается.

    Приметой служит сам язык или уровень CEFR, а не слово «свободный»:
    вздумай мы считать подтверждением его, заслон молча выключался бы на
    каждой вакансии со свободным графиком, и выдуманное требование языка
    уводило бы годную вакансию в отказ.
    """
    client = provider(
        {CHAT: fit_answer("reject", "вакансия подразумевает английский язык")}
    )
    profile = CandidateProfile(
        languages=[CandidateLanguage(name="Английский", level="A2")]
    )

    got = await _check(
        client,
        raw_text="Ищем питониста, свободный график, оформление по договору",
        profile=profile,
    )

    assert got.verdict == "fit"
    assert got.reason is None
