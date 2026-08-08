"""Следствия проверки вакансии на пригодность кандидату.

Вердиктов три: вакансия подходит, не подходит, или это вовсе не вакансия.
Поверх вердикта стоит защита от выдуманного обоснования: модель охотно
списывает причину отказа с примеров в промпте, и тогда в тексте объявления
её не найти.

Пойманное выдуманное обоснование разбирается по-разному. Отказ переворачивается
в «подходит»: пропустить лишнюю вакансию на ручной просмотр дешевле, чем
потерять настоящую. Мусор остаётся мусором, но без обоснования: сам пост
скорее всего и правда реклама, а пускать её в рассылку по перевороту нельзя.

Эти же тесты — единственный сторож `backend/llm/hallucination.py`: своего файла
у него нет, потому что снаружи он виден только перевёрнутым вердиктом.
"""

import json

import httpx
import pytest

from backend.llm.candidate import CandidateLanguage, CandidateProfile
from backend.llm.fit import _parse_fit_validation, validate_vacancy_fit
from tests.factories import parsed_vacancy
from tests.fakes.llm import CHAT, chat_response, provider


def _answer(verdict, reason=None) -> httpx.Response:
    """Ответ модели с вердиктом пригодности."""
    return chat_response(
        json.dumps({"verdict": verdict, "reason": reason}, ensure_ascii=False)
    )


async def _check(client, *, raw_text="обычный текст вакансии", profile=None):
    """Спросить модель о пригодности вакансии."""
    return await validate_vacancy_fit(
        parsed_vacancy(),
        raw_text,
        client,
        "qwen",
        profile=profile or CandidateProfile(),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("fit", "fit", id="подходит"),
        pytest.param("  REJECT  ", "reject", id="регистр и пробелы"),
        pytest.param("trash", "trash", id="не вакансия"),
    ],
)
def test_a_known_verdict_is_read(raw, expected):
    """Известный вердикт читается без учёта регистра и пробелов."""
    got = _parse_fit_validation(json.dumps({"verdict": raw, "reason": "почему"}))

    assert got.verdict == expected
    assert got.reason == "почему"


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param("не json вовсе", id="без объекта"),
        pytest.param('{"verdict": "может быть"}', id="неизвестный вердикт"),
        pytest.param('{"verdict": 42}', id="вердикт не строкой"),
        pytest.param('{"reason": "без вердикта"}', id="вердикта нет"),
    ],
)
def test_an_unusable_answer_yields_nothing(answer):
    """Неразбираемый ответ вердикта не даёт."""
    assert _parse_fit_validation(answer) is None


def test_an_empty_reason_becomes_absence():
    """Пустое обоснование становится отсутствием, а не пустой строкой."""
    got = _parse_fit_validation(json.dumps({"verdict": "fit", "reason": "   "}))

    assert got.reason is None


async def test_a_verdict_comes_back_with_its_reason():
    """Вердикт возвращается вместе с обоснованием."""
    client = provider({CHAT: _answer("reject", "требуется опыт в геймдеве")})

    got = await _check(client, raw_text="ищем разработчика с опытом в геймдеве")

    assert got.verdict == "reject"
    assert got.reason == "требуется опыт в геймдеве"


@pytest.mark.parametrize(
    "prepared",
    [
        pytest.param(httpx.Response(500, text="упал"), id="отказ провайдера"),
        pytest.param(httpx.ConnectError("сеть отвалилась"), id="обрыв связи"),
        pytest.param(httpx.Response(200, json={"нет": "выборов"}), id="чужая форма"),
        pytest.param(chat_response("я не понял"), id="неразбираемый ответ"),
    ],
)
async def test_trouble_yields_no_verdict(prepared):
    """Беда с провайдером вердикта не даёт и наружу не пробрасывается."""
    client = provider({CHAT: prepared})

    assert await _check(client) is None


async def test_a_made_up_reason_for_rejection_flips_the_verdict():
    """Выдуманное обоснование отказа переворачивает вердикт в «подходит».

    Модель сослалась на требование к языку, которого в объявлении нет.
    Пропустить такую вакансию на ручной просмотр дешевле, чем потерять
    настоящую из-за фантазии модели.
    """
    client = provider(
        {CHAT: _answer("reject", "вакансия подразумевает английский язык")}
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
    client = provider({CHAT: _answer("reject", "требуется уровень B2")})

    got = await _check(
        client,
        raw_text="Ищем питониста в бэкенд, оформление по договору",
        profile=CandidateProfile(),
    )

    assert got.verdict == "fit"
    assert got.reason is None


async def test_a_level_named_in_the_post_is_not_taken_for_a_made_up_one():
    """Уровень, названный в объявлении, выдумкой не считается."""
    client = provider({CHAT: _answer("reject", "требуется уровень B2")})

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
        {CHAT: _answer("reject", "вакансия подразумевает английский язык")}
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


async def test_a_made_up_reason_for_junk_keeps_the_verdict_but_drops_the_reason():
    """У мусора выдуманное обоснование стирается, а вердикт остаётся.

    Переворачивать мусор в «подходит» нельзя: реклама ушла бы в рассылку.
    А само обоснование бессмысленно, и показывать его пользователю незачем.
    """
    client = provider(
        {CHAT: _answer("trash", "вакансия подразумевает английский язык")}
    )
    profile = CandidateProfile(
        languages=[CandidateLanguage(name="Английский", level="A2")]
    )

    got = await _check(
        client, raw_text="Подпишись на канал, скидки на курсы!", profile=profile
    )

    assert got.verdict == "trash"
    assert got.reason is None


async def test_a_fitting_verdict_is_never_second_guessed():
    """Вердикт «подходит» на выдуманность не проверяют.

    Проверка нужна там, где вакансия отбрасывается: пропущенная лишняя
    вакансия видна пользователю, а отброшенная — нет.
    """
    client = provider(
        {CHAT: _answer("fit", "вакансия подразумевает английский язык")}
    )
    profile = CandidateProfile(
        languages=[CandidateLanguage(name="Английский", level="A2")]
    )

    got = await _check(client, raw_text="Ищем питониста.", profile=profile)

    assert got.verdict == "fit"
    assert got.reason == "вакансия подразумевает английский язык"


async def test_a_verdict_without_a_reason_is_not_second_guessed():
    """Вердикт без обоснования на выдуманность не проверяют — проверять нечего."""
    client = provider({CHAT: _answer("reject", None)})

    got = await _check(client, raw_text="Ищем питониста.")

    assert got.verdict == "reject"
    assert got.reason is None


async def test_a_reason_speaking_about_the_candidate_is_treated_as_made_up():
    """Обоснование, говорящее о кандидате, а не о вакансии, считается выдуманным.

    Обоснование должно называть требование вакансии. Пересказ данных
    кандидата означает, что модель ушла в рассуждение вместо цитаты — и
    такой отказ переворачивается независимо от текста объявления.
    """
    client = provider({CHAT: _answer("reject", "у кандидата только B1")})

    got = await _check(client, raw_text="Ищем питониста, английский B1 и выше.")

    assert got.verdict == "fit"
    assert got.reason is None


async def test_a_reason_naming_the_requirement_is_left_alone():
    """Обоснование, называющее требование вакансии, не трогают.

    Разница с соседним случаем — в том, о ком речь: «нужен C1» описывает
    вакансию, «у кандидата только B1» описывает кандидата.
    """
    client = provider({CHAT: _answer("reject", "нужен C1, это выше нашего уровня")})

    got = await _check(client, raw_text="Ищем питониста, английский C1.")

    assert got.verdict == "reject"
    assert got.reason == "нужен C1, это выше нашего уровня"
