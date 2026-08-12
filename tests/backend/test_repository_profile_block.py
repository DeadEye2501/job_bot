"""Следствия сборки блока «Информация о кандидате» для письма-отклика.

Блок уходит в запрос к языковой модели, поэтому незаполненные поля не просто
выглядят некрасиво — они попадают в письмо. Пустое поле пропускается целиком,
а не превращается в строку «Роль: не указано».
"""

from datetime import date

from backend.repository.profile_block import build_profile_block
from tests.dbio import put
from tests.factories import experience_row, profile_row, profile_skill_row


async def test_without_a_profile_the_block_is_empty(session):
    """Без профиля блок пуст — вставлять в письмо нечего."""
    assert await build_profile_block(session) == ""


async def test_an_unfilled_field_is_skipped_rather_than_named(
    session, session_factory
):
    """Незаполненное поле пропускается, а не называется пустым.

    Иначе в запрос ушло бы «Локация: None», и модель попыталась бы это
    обыграть в письме.
    """
    await put(session_factory, profile_row(title="Разработчик", location=None))

    block = await build_profile_block(session)

    assert "Локация" not in block
    assert "None" not in block
    assert "Роль: Разработчик" in block


async def test_an_empty_role_is_skipped_too(session, session_factory):
    """Пустая роль пропускается так же, как незаполненная.

    Роль объявлена обязательной, поэтому пустоты в ней не бывает — но
    пустая строка бывает, и охрана рассчитана на неё. Проверено мутацией:
    без этого случая охрану можно было выбросить незаметно.
    """
    await put(session_factory, profile_row(title="", location="Тбилиси"))

    block = await build_profile_block(session)

    assert "Роль" not in block
    assert "Локация: Тбилиси" in block


async def test_the_name_is_joined_from_both_halves(session, session_factory):
    """Имя склеивается из двух половин, и пустая половина не даёт лишнего пробела."""
    await put(session_factory, profile_row(first_name="Иван", last_name="Петров"))
    both = await build_profile_block(session)

    assert "Имя: Иван Петров" in both


async def test_skills_are_grouped_by_category(session, session_factory):
    """Навыки в блоке сгруппированы по своим разделам."""
    profile = profile_row()
    await put(session_factory, profile)
    await put(
        session_factory,
        profile_skill_row(profile.id, "Python", category="языки"),
        profile_skill_row(profile.id, "Postgres", category="базы"),
        profile_skill_row(profile.id, "Go", category="языки"),
    )

    block = await build_profile_block(session)

    assert "- языки: Python, Go" in block
    assert "- базы: Postgres" in block


async def test_places_are_listed_newest_first_with_their_span(
    session, session_factory
):
    """Места работы перечислены от свежего к давнему, каждое со сроком.

    У текущего места вместо даты окончания стоит «настоящее время»: пустая
    дата в письме читалась бы как обрыв.
    """
    profile = profile_row()
    await put(session_factory, profile)
    await put(
        session_factory,
        experience_row(
            profile.id,
            company="Давняя",
            role="Младший",
            start_date=date(2018, 3, 1),
            end_date=date(2020, 2, 29),
        ),
        experience_row(
            profile.id,
            company="Нынешняя",
            role="Старший",
            start_date=date(2020, 3, 1),
            end_date=None,
        ),
    )

    block = await build_profile_block(session)
    places = [line for line in block.splitlines() if line.startswith("- ")]

    assert places == [
        "- Нынешняя (Старший, 03.2020 — настоящее время)",
        "- Давняя (Младший, 03.2018 — 02.2020)",
    ]


async def test_the_first_achievement_joins_the_place(session, session_factory):
    """К месту работы приписывается первое достижение, если оно есть."""
    profile = profile_row()
    await put(session_factory, profile)
    await put(
        session_factory,
        experience_row(
            profile.id,
            company="Контур",
            role="Разработчик",
            start_date=date(2020, 1, 1),
            achievements=["ускорил сборку втрое", "второе достижение"],
        ),
    )

    block = await build_profile_block(session)

    assert "ускорил сборку втрое" in block
    assert "второе достижение" not in block


async def test_the_years_count_from_the_earliest_place(session, session_factory):
    """Годы опыта считаются от самого раннего места работы.

    Обе даты отсчитываются от текущего года, а не зашиты числом: с зашитой
    поздней датой тест сломался бы сам собой в тот год, когда она станет
    старше вычисленной ранней.
    """
    profile = profile_row()
    await put(session_factory, profile)
    started = date(date.today().year - 7, 1, 1)
    later = date(date.today().year - 2, 1, 1)
    await put(
        session_factory,
        experience_row(profile.id, company="Поздняя", start_date=later),
        experience_row(profile.id, company="Ранняя", start_date=started),
    )

    block = await build_profile_block(session)

    assert "Опыт: 7+ лет в IT" in block


async def test_without_any_place_the_years_are_not_mentioned(
    session, session_factory
):
    """Без единого места работы годы опыта не называются вовсе.

    Рядом проверяется, что блок не пуст: без этого проверка прошла бы и
    тогда, когда сборка не собрала ничего.
    """
    await put(session_factory, profile_row(title="Разработчик"))

    block = await build_profile_block(session)

    assert "Роль: Разработчик" in block
    assert "Опыт:" not in block


async def test_free_preferences_go_into_their_own_section(session, session_factory):
    """Свободные пожелания идут отдельным разделом, если заполнены."""
    await put(
        session_factory,
        profile_row(free_preferences="  готов к переезду в Европу  "),
    )

    block = await build_profile_block(session)

    assert block.endswith("Дополнительно:\nготов к переезду в Европу")


async def test_an_empty_preferences_field_adds_no_section(session, session_factory):
    """Пустые пожелания раздела не добавляют.

    Рядом проверяется, что блок не пуст: без этого проверка прошла бы и
    тогда, когда сборка не собрала ничего.
    """
    await put(session_factory, profile_row(title="Разработчик", free_preferences=None))

    block = await build_profile_block(session)

    assert "Роль: Разработчик" in block
    assert "Дополнительно" not in block
