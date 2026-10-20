"""Заявка окна «Добавить вакансию», которую ведёт бот: поля с переключателем, текст.

Поля с выключенным переключателем бот не видит — их заводит мост сам; сюда они
приходят, только когда заведённое надо отдать откликателю.
"""

import pytest

from backend.flows.hand_made import HandRequest, ingest_by_hand
from backend.flows.hand_outcome import HandResult
from backend.models import Vacancy
from tests.dbio import all_rows, only_row, put
from tests.factories import vacancy_row
from tests.fakes.agent import kit_for


def _fields(**overrides) -> dict:
    """Поля формы так, как их прочитал мост (`read_new_vacancy_fields`)."""
    return {
        "title": "Python-разработчик", "company_id": None, "hr_id": None, "source_url": None,
        "location": None, "remote": None, "grade": None, "salary_min": None, "salary_max": None,
        "salary_currency": None, "stack_required": ["Python"], "stack_preferred": [],
        "description": "Набрано руками", "notes": None, "posted_at": None, **overrides,
    }


@pytest.fixture
async def filing(make_pipeline):
    """Конвейер, у которого весть окну и отклик пишутся в один след `order`."""
    pipeline = await make_pipeline()
    pipeline.told = []
    pipeline.order = []

    def told(result):
        pipeline.told.append(result)
        pipeline.order.append("весть")

    async def apply(ids):
        pipeline.applied.append(ids)
        pipeline.order.append("отклик")

    pipeline.on_hand_made = told
    pipeline.apply = apply
    return pipeline


async def test_fields_with_the_switch_are_filed_and_handed_over(filing, session_factory):
    """Набранное человеком — уже готовый разбор: модель его не трогает, строка
    в New, откликатель зван по режиму."""
    await ingest_by_hand(kit_for(filing), HandRequest("fields", _fields(), None, True))

    saved = await only_row(session_factory, Vacancy)
    assert (saved.title, saved.description, saved.raw_text, saved.is_parsed) == (
        "Python-разработчик", "Набрано руками", None, True,
    )
    assert filing.told == [HandResult("ok", saved.id)]
    assert filing.applied == [[saved.id]]
    assert filing.order == ["весть", "отклик"]


async def test_fields_of_a_page_filed_before_are_not_handed_over(filing, session_factory):
    """Повтор не заводится и не отдаётся: окно переходит на существующую."""
    existing = vacancy_row(source_url="https://hh.ru/vacancy/123")
    await put(session_factory, existing)

    await ingest_by_hand(
        kit_for(filing), HandRequest("fields", _fields(source_url="https://hh.ru/vacancy/123"), None, True)
    )

    assert len(await all_rows(session_factory, Vacancy)) == 1
    assert filing.told == [HandResult("duplicate", existing.id)]
    assert filing.applied == []
