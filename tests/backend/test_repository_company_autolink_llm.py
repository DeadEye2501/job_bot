"""Следствия обращения к языковой модели при сведении компаний.

К модели идут только похожие кандидаты, и только когда правила не сработали:
«Сбер» и «Сбербанк» правилом имени не сходятся — приведённые формы у них
разные, — но и разными компаниями считать их нельзя. Ответ модели проверяется:
она вправе назвать номер, которого ей не давали, и такой ответ не принимается.
"""

import pytest

from backend.models import ProfileLanguage
from backend.repository.companies_matching import find_or_create_company
from tests.dbio import put
from tests.factories import company_row, profile_row


class Arbiter:
    """Подделка арбитра: отдаёт заранее положенный ответ и запоминает вопрос."""

    def __init__(self, *, matched_id=None, reasoning="так решил"):
        self._matched_id = matched_id
        self._reasoning = reasoning
        self.calls: list[dict] = []

    async def __call__(self, client, model, ask):
        self.calls.append(
            {
                "client": client,
                "model": model,
                "parsed_name": ask.parsed_name,
                "parsed_website": ask.parsed_website,
                "candidate_names": [c.name for c in ask.candidates],
                "language": ask.language,
            }
        )
        return self._matched_id, self._reasoning


@pytest.fixture
def arbiter(monkeypatch):
    """Подставляет подделку арбитра и отдаёт её тесту.

    Боевой код ввозит арбитра внутри функции, а не сверху файла, поэтому
    подмена атрибута модуля срабатывает: связывание происходит в момент
    вызова.
    """

    def install(**kwargs) -> Arbiter:
        fake = Arbiter(**kwargs)
        monkeypatch.setattr("backend.llm.company.dedupe_company_with_llm", fake)
        return fake

    return install


async def resolve(session, name, arbiter_fake=None, **kwargs):
    """Свести имя к компании, обращаясь к арбитру, если он подставлен."""
    return await find_or_create_company(
        session,
        name,
        lm_client=object() if arbiter_fake is not None else None,
        lm_model="qwen" if arbiter_fake is not None else None,
        **kwargs,
    )


async def test_without_an_arbiter_the_scheme_degrades_to_rules_and_creation(
    session, session_factory, arbiter
):
    """Без арбитра похожее имя не сводится, а заводится новой строкой."""
    fake = arbiter()
    await put(session_factory, company_row(name="Сбербанк", website=None))

    company, decision = await find_or_create_company(session, "Сбер")

    assert decision["stage"] == "create"
    assert company.name == "Сбер"
    assert fake.calls == []


async def test_a_similar_name_is_taken_to_the_arbiter(
    session, session_factory, arbiter
):
    """Похожее имя уходит к арбитру, и его ответ принимается."""
    existing = company_row(name="Сбербанк", website=None)
    await put(session_factory, existing)
    fake = arbiter(matched_id=existing.id, reasoning="одна и та же компания")

    company, decision = await resolve(session, "Сбербанк Тех", fake)

    assert company.id == existing.id
    assert decision["stage"] == "llm_match"
    assert decision["llm_reasoning"] == "одна и та же компания"
    assert fake.calls[0]["candidate_names"] == ["Сбербанк"]


async def test_the_arbiter_explains_in_the_person_language(session, session_factory, arbiter):
    """Пояснение арбитра читает человек: язык ему решает приложение по анкете."""
    person = profile_row()
    await put(session_factory, person)
    await put(session_factory, ProfileLanguage(profile_id=person.id, language="Қазақша", level="native"))
    await put(session_factory, company_row(name="Сбербанк", website=None))
    fake = arbiter()

    await resolve(session, "Сбербанк Тех", fake)

    assert fake.calls[0]["language"] == "Қазақша"


async def test_a_name_far_from_everything_never_reaches_the_arbiter(
    session, session_factory, arbiter
):
    """Ничем не похожее имя к арбитру не идёт вовсе.

    Порог похожести отсекает вызовы, за которые нечем платить: у «Ромашки»
    и «Сбербанка» общего нет.
    """
    await put(session_factory, company_row(name="Сбербанк", website=None))
    fake = arbiter(matched_id=1)

    company, decision = await resolve(session, "Ромашка", fake)

    assert fake.calls == []
    assert decision["stage"] == "create"
    assert decision["candidates"] is None
    assert company.name == "Ромашка"


async def test_a_candidate_with_a_conflicting_website_is_not_offered(
    session, session_factory, arbiter
):
    """Кандидат с другим настоящим сайтом к арбитру не попадает.

    Жёсткое правило по сайтам действует и до обращения к модели: спрашивать
    о том, что уже решено, незачем.
    """
    conflicting = company_row(name="Сбербанк", website="https://sber.ru")
    plain = company_row(name="Сбербанк Технологии", website=None)
    await put(session_factory, conflicting, plain)
    fake = arbiter(matched_id=plain.id)

    await resolve(session, "Сбербанк Тех", fake, website="https://other.example")

    assert fake.calls[0]["candidate_names"] == ["Сбербанк Технологии"]


async def test_the_arbiter_sees_at_most_five_closest_candidates(
    session, session_factory, arbiter
):
    """Арбитру показывают не больше пяти кандидатов, и самых близких.

    Шесть похожих имён заведены так, что порядок вставки обратен порядку
    близости: без сортировки в список попали бы не те пять.
    """
    await put(
        session_factory,
        *[
            company_row(name="Сбербанк" + "a" * n, website=None)
            for n in range(6, 0, -1)
        ],
    )
    fake = arbiter()

    await resolve(session, "Сбербанк", fake)

    assert fake.calls[0]["candidate_names"] == [
        "Сбербанкa",
        "Сбербанкaa",
        "Сбербанкaaa",
        "Сбербанкaaaa",
        "Сбербанкaaaaa",
    ]


async def test_the_similarity_threshold_cuts_right_where_it_says(
    session, session_factory, arbiter
):
    """Порог схожести отсекает соседа, отличающегося от прошедшего на один знак.

    Приведённые формы: образец «sberbank» в восемь знаков, у прошедшего
    четырнадцать, у отсечённого пятнадцать. Отношение совпадения — 0,727 и
    0,696 против порога 0,7. Пара выбрана вплотную к границе нарочно: на
    заведомо далёком имени порог можно было бы опустить хоть до нуля, и
    ничего бы не покраснело.
    """
    await put(
        session_factory,
        company_row(name="Сбербанк" + "a" * 6, website=None),
        company_row(name="Сбербанк" + "a" * 7, website=None),
    )
    fake = arbiter()

    await resolve(session, "Сбербанк", fake)

    assert fake.calls[0]["candidate_names"] == ["Сбербанкaaaaaa"]


async def test_a_refusal_by_the_arbiter_leads_to_a_new_row(
    session, session_factory, arbiter
):
    """Отказ арбитра приводит к новой строке, и это видно по решению.

    Отметка «модель спрашивали и она отказала» сохраняется отдельно: иначе
    по записи не отличить её от «модель не спрашивали вовсе».
    """
    await put(session_factory, company_row(name="Сбербанк", website=None))
    fake = arbiter(matched_id=None, reasoning="разные конторы")

    company, decision = await resolve(session, "Сбербанк Тех", fake)

    assert company.name == "Сбербанк Тех"
    assert decision["stage"] == "create"
    assert decision["pre_create_stage"] == "llm_no_match"
    assert decision["llm_reasoning"] == "разные конторы"
    assert [c["name"] for c in decision["candidates"]] == ["Сбербанк"]


async def test_an_answer_outside_the_shortlist_is_not_accepted(
    session, session_factory, arbiter
):
    """Номер, которого арбитру не давали, не принимается.

    Модель вправе выдумать номер, и склеивание необратимо на уровне
    вакансии. Выдуманный номер записывается отдельным полем решения, чтобы
    его было видно потом.
    """
    shown = company_row(name="Сбербанк", website=None)
    hidden = company_row(name="Ромашка", website=None)
    await put(session_factory, shown, hidden)
    fake = arbiter(matched_id=hidden.id)

    company, decision = await resolve(session, "Сбербанк Тех", fake)

    assert company.name == "Сбербанк Тех"
    assert decision["stage"] == "create"
    assert decision["llm_hallucinated_id"] == hidden.id


async def test_a_name_reduced_to_nothing_never_reaches_the_arbiter(
    session, session_factory, arbiter
):
    """Имя, свёдшееся к пустоте, к арбитру не идёт.

    Сравнение пустого с пустым даёт полное сходство, и «голые» юридические
    формы ушли бы к арбитру все скопом.
    """
    await put(session_factory, company_row(name="ООО", website=None))
    fake = arbiter(matched_id=1)

    _, decision = await resolve(session, "ПАО", fake)

    assert fake.calls == []
    assert decision["stage"] == "create"
