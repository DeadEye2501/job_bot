"""Следствия автоматического сведения разобранной компании к существующей.

Разбор вакансии отдаёт пару «имя, сайт», и её надо свести к строке в базе или
завести новую. Правил три, они пробуются по порядку: точное совпадение
приведённого имени, совпадение с одним из написаний, совпадение хоста. Поверх
всех трёх лежит жёсткое правило: у двух записей указаны разные настоящие
сайты — это разные компании, сколько бы ни совпадали имена.

Ответственность файла — исход сведения без обращения к языковой модели: к
какой строке свелась разобранная пара и что с этой строкой стало. Заведение
новой и обогащение найденной сюда входят: это два возможных исхода того же
вызова, а не соседние предметы. Обращение к модели — соседний файл: без неё
схема вырождается в правила плюс заведение.
"""

from sqlalchemy import select

from backend.models import Company
from backend.repository.companies_matching import _create_company_row, find_or_create_company
from tests.dbio import put
from tests.factories import company_row


async def test_an_empty_name_resolves_to_nothing(session, session_factory):
    """Пустое имя не сводится ни к чему и новой строки не заводит."""
    await put(session_factory, company_row(name="Контур"))

    company, decision = await find_or_create_company(session, "   ")

    assert company is None
    assert decision["stage"] == "skip"
    assert len((await session.scalars(select(Company))).all()) == 1


async def test_a_different_spelling_of_the_same_name_matches(
    session, session_factory
):
    """Другое написание того же имени сводится к существующей строке."""
    existing = company_row(name="ПАО Сбербанк", website=None)
    other = company_row(name="Ромашка")
    await put(session_factory, existing, other)

    company, decision = await find_or_create_company(session, 'ООО "Sberbank"')

    assert company.id == existing.id
    assert decision["stage"] == "rule_name"
    assert decision["matched_id"] == existing.id


async def test_a_known_alias_matches(session, session_factory):
    """Совпадение с записанным написанием тоже сводит к существующей строке."""
    existing = company_row(name="СКБ Контур", aliases=["Kontur"], website=None)
    other = company_row(name="Ромашка")
    await put(session_factory, existing, other)

    company, decision = await find_or_create_company(session, "контур")

    assert company.id == existing.id
    assert decision["stage"] == "rule_alias"


async def test_a_conflicting_website_blocks_the_alias_rule_too(
    session, session_factory
):
    """Другой настоящий сайт запирает и правило написаний, не только имени.

    Иначе жёсткое правило обходилось бы через список написаний: имя не
    совпало, зато совпало написание — и две разные компании склеились бы.
    """
    existing = company_row(
        name="СКБ Контур", aliases=["Kontur"], website="https://kontur.ru"
    )
    await put(session_factory, existing)

    company, decision = await find_or_create_company(
        session, "kontur", website="https://other.example"
    )

    assert company.id != existing.id
    assert decision["stage"] == "create"


async def test_a_matching_website_joins_records_with_different_names(
    session, session_factory
):
    """Общий настоящий сайт сводит записи даже при разных именах.

    Корпоративный домен — сильный признак: так выглядят переименование,
    бренд против юридического названия и разнобой парсера на одной странице.
    """
    existing = company_row(name="Контур", website="https://kontur.ru")
    await put(session_factory, existing)

    company, decision = await find_or_create_company(
        session, "СКБ Контур", website="http://www.kontur.ru/jobs"
    )

    assert company.id == existing.id
    assert decision["stage"] == "rule_website"


async def test_a_link_to_a_channel_does_not_join_anything(session, session_factory):
    """Ссылка на канал сайтом не считается и записи по себе не сводит."""
    existing = company_row(name="Контур", website="https://t.me/kontur")
    await put(session_factory, existing)

    company, decision = await find_or_create_company(
        session, "Ромашка", website="https://t.me/kontur"
    )

    assert company.id != existing.id
    assert decision["stage"] == "create"


async def test_a_name_reduced_to_a_bare_legal_form_never_matches_by_name(
    session, session_factory
):
    """Имя, свёдшееся к пустоте, по имени ни с чем не сходится.

    «ООО» и «ПАО» после срезания юридической формы дают пустую строку, и
    сравнение пустого с пустым склеило бы заведомо разные компании.
    """
    existing = company_row(name="ООО", website=None)
    await put(session_factory, existing)

    company, decision = await find_or_create_company(session, "ПАО")

    assert company.id != existing.id
    assert decision["stage"] == "create"


async def test_the_parsed_name_is_remembered_as_a_new_spelling(
    session, session_factory
):
    """Написание из объявления запоминается, если такого ещё не было.

    Сведение здесь идёт по сайту, а не по имени: имена как раз разные, и
    именно поэтому новое написание есть смысл запомнить — в следующий раз
    оно сработает уже правилом написаний, без обращения к сайту.
    """
    existing = company_row(name="СКБ Контур", aliases=[], website="https://kontur.ru")
    await put(session_factory, existing)

    _, decision = await find_or_create_company(
        session, "  Контур  ", website="https://kontur.ru"
    )

    assert decision["stage"] == "rule_website"
    assert (await session.get(Company, existing.id)).aliases == ["Контур"]


async def test_a_spelling_already_known_is_not_remembered_twice(
    session, session_factory
):
    """Уже известное написание вторым разом не запоминается."""
    existing = company_row(name="СКБ Контур", aliases=["Kontur"], website=None)
    await put(session_factory, existing)

    await find_or_create_company(session, "kontur")

    assert (await session.get(Company, existing.id)).aliases == ["Kontur"]


async def test_a_real_website_fills_an_empty_slot_but_never_replaces_one(
    session, session_factory
):
    """Настоящий сайт из объявления заполняет пустое поле, но не затирает своё.

    Во второй половине сайт из объявления нарочно отличается от записанного:
    подай тот же — и «не затирает» стало бы неотличимо от «затирает тем же».
    Правило о разных сайтах здесь не мешает: сведение идёт по написанию,
    добавленному в предыдущем вызове, и хосты сравниваются только у правил
    имени и написаний, а до них дело доходит именно потому, что сайты разные.
    """
    empty = company_row(name="Контур", website=None)
    filled = company_row(name="Ромашка", aliases=["Romashka"], website="https://romashka.ru")
    await put(session_factory, empty, filled)

    await find_or_create_company(session, "Контур", website="https://kontur.ru")
    await find_or_create_company(session, "Ромашка", website="https://kontur.dev")

    assert (await session.get(Company, empty.id)).website == "https://kontur.ru"
    assert (await session.get(Company, filled.id)).website == "https://romashka.ru"


async def test_a_channel_link_never_becomes_a_website(session, session_factory):
    """Ссылка на канал сайтом компании не записывается — ни в старую, ни в новую.

    Показанная пользователю как «официальный сайт», она врёт, а будущие
    сравнения по хосту из неё ничего не извлекут.
    """
    existing = company_row(name="Контур", website=None)
    await put(session_factory, existing)

    await find_or_create_company(session, "Контур", website="https://t.me/kontur")
    fresh, _ = await find_or_create_company(
        session, "Ромашка", website="https://t.me/romashka"
    )

    assert (await session.get(Company, existing.id)).website is None
    assert fresh.website is None


async def test_a_new_company_is_created_when_nothing_matches(
    session, session_factory
):
    """Когда ни одно правило не сработало, заводится новая строка."""
    await put(session_factory, company_row(name="Контур"))

    company, decision = await find_or_create_company(
        session, "Ромашка", website="https://romashka.ru"
    )

    assert decision["stage"] == "create"
    assert decision["matched_id"] == company.id
    assert company.name == "Ромашка"
    assert company.aliases == []
    assert len((await session.scalars(select(Company))).all()) == 2


async def test_the_same_name_with_a_different_website_folds_into_the_old_row(
    session, session_factory
):
    """Имя решает: компания с таким же именем — та же самая.

    Правила сведения разные сайты не склеивают, а завести вторую строку не
    даёт уникальность имени: вставка срывается, и старую запись отдаёт
    пересмотр. **Решение человека от 10 августа 2026: так и остаётся.**
    Имена компаний на практике не пересекаются, а разделение их по сайту
    потребовало бы правки схемы и сняло бы защиту от двух одинаковых
    строк без сайта вовсе.

    Стадия называет это сведением по имени, а не гонкой: строку было видно
    в выборке, с которой начинался разбор, и в ленте вакансии ярлык
    остаётся навсегда — по нему потом отличают рядовой случай от настоящей
    гонки вставок.
    """
    existing = company_row(name="Контур", website="https://kontur.ru")
    await put(session_factory, existing)

    company, decision = await find_or_create_company(
        session, "Контур", website="https://kontur.dev"
    )

    assert company.id == existing.id
    assert decision["stage"] == "rule_name_unique"
    assert len((await session.scalars(select(Company))).all()) == 1


async def test_a_row_that_appeared_after_the_lookup_is_called_a_race(
    session, session_factory
):
    """Строка, которой в выборке не было, помечается гонкой вставок.

    Через `find_or_create_company` этот случай не изобразить: выборка читает
    все строки разом, и любая существующая в ней есть. Чужой писатель между
    выборкой и вставкой тоже не вклинится — к этому мигу база уже держит
    запись на нас. Поэтому заведение зовётся напрямую с тем же перечнем
    увиденного, который оно получает от разбора.

    Перечень непустой нарочно: в нём номер соседней строки, а не
    столкнувшейся. С пустым проверка сторожила бы «выборка вообще пуста», и
    подмена условия на такую прошла бы незамеченной.
    """
    existing = company_row(name="Контур", website="https://kontur.ru")
    other = company_row(name="Ромашка")
    await put(session_factory, existing, other)
    decision = {"stage": "skip", "matched_id": None}

    company, decision = await _create_company_row(
        session, "Контур", "https://kontur.dev", decision, {other.id}
    )

    assert company.id == existing.id
    assert decision["stage"] == "create_race_fallback"
