"""Следствия сопоставления HR со строками чёрного списка.

Одного человека в списке можно записать двумя способами — ником или
идентификатором Telegram, — и написание выбирают в момент добавления, когда
известно не всё. Поэтому поиск проверяет оба, а кнопка «добавить» пишет одно —
несменяемое.
"""

from backend.models import HR
from backend.repository.blacklist_marks import preferred_blacklist_value
from backend.repository.hr_card import (
    get_hr_detail,
    hr_blacklist_candidates,
    merge_hr,
)
from tests.dbio import put
from tests.factories import blacklist_row, hr_row


def test_both_spellings_are_offered_for_lookup():
    """Для поиска предлагаются оба написания сразу, несменяемое первым."""
    hr = hr_row(telegram_username="maria", telegram_user_id=111)

    assert hr_blacklist_candidates(hr) == ["user_id:111", "@maria"]


def test_a_missing_identifier_drops_its_spelling():
    """Отсутствующий признак своего написания не даёт."""
    assert hr_blacklist_candidates(
        hr_row(telegram_username="maria", telegram_user_id=None)
    ) == ["@maria"]
    assert hr_blacklist_candidates(
        hr_row(telegram_username=None, telegram_user_id=111)
    ) == ["user_id:111"]
    assert hr_blacklist_candidates(
        hr_row(telegram_username=None, telegram_user_id=None)
    ) == []


def test_the_button_writes_the_spelling_that_cannot_change():
    """Кнопка добавления пишет номер учётной записи, а к нику отступает без него.

    Ник у собеседника сменяемый, и Telegram переписывает его в карточке при
    каждом входящем письме; номер не меняется никогда. Читается на экране
    хуже, но отметка, слетающая от смены ника, не отсеивает никого.
    """
    def written(**identity) -> str | None:
        return preferred_blacklist_value(hr_blacklist_candidates(hr_row(**identity)))

    assert written(telegram_username="maria", telegram_user_id=111) == "user_id:111"
    assert written(telegram_username="maria", telegram_user_id=None) == "@maria"
    assert written(telegram_username=None, telegram_user_id=None) is None


async def test_a_mark_survives_a_renamed_account(session, session_factory):
    """Отметка держится, когда собеседник сменил ник.

    Ровно за этим кнопка и пишет номер: Telegram отдаёт новый ник с первым же
    письмом, карточка его перезаписывает — и отметка, заведённая на прежний,
    перестала бы совпадать. Отсев тогда молча снимается, а строка в списке
    продолжает гореть: на экране всё выглядит так, будто он работает.
    """
    hr = hr_row(name="Анна", telegram_username="Recruiter_Anna", telegram_user_id=777)
    await put(session_factory, hr)
    await put(session_factory, blacklist_row("hr", "user_id:777"))

    async with session_factory() as telegram_said:
        row = await telegram_said.get(HR, hr.id)
        row.telegram_username = "recruiter_anna"
        await telegram_said.commit()

    assert (
        await get_hr_detail(session, hr.id)
    ).blacklist_value == "user_id:777"


async def test_the_card_shows_the_mark_written_under_either_spelling(
    session, session_factory
):
    """Карточка находит отметку, каким бы из двух написаний её ни завели.

    Запись могли добавить, когда у нас был только ник, а идентификатор
    появился позже — и наоборот.
    """
    by_username = hr_row(name="по нику", telegram_username="maria", telegram_user_id=111)
    by_id = hr_row(name="по номеру", telegram_username="olga", telegram_user_id=222)
    await put(session_factory, by_username, by_id)
    await put(
        session_factory,
        blacklist_row("hr", "@maria"),
        blacklist_row("hr", "user_id:222"),
    )

    assert (await get_hr_detail(session, by_username.id)).blacklist_value == "@maria"
    assert (await get_hr_detail(session, by_id.id)).blacklist_value == "user_id:222"


async def test_a_switched_off_mark_does_not_show(session, session_factory):
    """Выключенная отметка в карточке не показывается.

    Строку из списка не удаляют, а гасят: история решений остаётся, но на
    поведение не влияет.
    """
    hr = hr_row(telegram_username="maria", telegram_user_id=111)
    await put(session_factory, hr)
    await put(session_factory, blacklist_row("hr", "@maria", active=False))

    assert (await get_hr_detail(session, hr.id)).blacklist_value is None


async def test_a_mark_of_another_kind_does_not_show(session, session_factory):
    """Отметка другого рода к HR не относится.

    В одной таблице лежат записи и про людей, и про каналы, и про компании;
    совпадение значения между родами возможно.
    """
    hr = hr_row(telegram_username="maria", telegram_user_id=111)
    await put(session_factory, hr)
    await put(session_factory, blacklist_row("channel", "@maria"))

    assert (await get_hr_detail(session, hr.id)).blacklist_value is None


async def test_when_both_spellings_are_listed_the_older_row_wins(
    session, session_factory
):
    """Когда заведены оба написания, показывается заведённое раньше.

    Проверяется направление упорядочивания, а не сам его факт: на двух
    строках база и без сортировки вернула бы их в порядке вставки, и от
    снятия `ORDER BY` тест не покраснеет. Доказать необходимость самой
    сортировки здесь нечем — порядок без неё не определён, но на таком
    наборе совпадает с нужным. Переворот направления ловится.
    """
    hr = hr_row(telegram_username="maria", telegram_user_id=111)
    await put(session_factory, hr)
    await put(
        session_factory,
        blacklist_row("hr", "user_id:111"),
        blacklist_row("hr", "@maria"),
    )

    assert (await get_hr_detail(session, hr.id)).blacklist_value == "user_id:111"


async def test_a_mark_moves_onto_the_survivor_of_a_merge(session, session_factory):
    """Отметка поглощённой карточки достаётся выжившей.

    Отсеянного человека легко завести дважды и потом слить: его учётная
    запись при слиянии пропадает, а с ней пропала бы и отметка — заслон
    отправки перестал бы его видеть, и бот написал бы заблокированному.
    """
    absorbed = hr_row(name="дубль", telegram_username="olga", telegram_user_id=222)
    survivor = hr_row(name="основной", telegram_username="maria", telegram_user_id=111)
    await put(session_factory, absorbed, survivor)
    await put(session_factory, blacklist_row("hr", "user_id:222"))

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (await get_hr_detail(session, survivor.id)).blacklist_value == "user_id:111"


async def test_a_mark_keeps_working_when_the_account_moves_to_the_survivor(
    session, session_factory
):
    """Отметка остаётся действующей и когда переезжает сама учётная запись.

    У выжившего своей записи не было — он получает чужую целиком, и написание
    отметки остаётся тем же. Переписывать тут нечего, но и потеряться она не
    должна.
    """
    absorbed = hr_row(name="дубль", telegram_username="olga", telegram_user_id=222)
    survivor = hr_row(name="основной", telegram_username=None, telegram_user_id=None)
    await put(session_factory, absorbed, survivor)
    await put(session_factory, blacklist_row("hr", "user_id:222"))

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (await get_hr_detail(session, survivor.id)).blacklist_value == "user_id:222"


async def test_the_survivors_own_mark_follows_a_replaced_nickname(
    session, session_factory
):
    """Отметка выжившего переезжает, когда его ник заместил чужой.

    У выжившего был один ник и отметка на нём; поглощённый принёс учётную
    запись, и ник карточки переписался. Отметка на прежнем нике не совпадает
    больше ни с кем: заслон отправки человека не видит, а строка списка
    продолжает отсеивать посты по нику, который теперь чужой.
    """
    absorbed = hr_row(name="дубль", telegram_username="olga", telegram_user_id=222)
    survivor = hr_row(name="основной", telegram_username="anna", telegram_user_id=None)
    await put(session_factory, absorbed, survivor)
    await put(session_factory, blacklist_row("hr", "@anna"))

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (await get_hr_detail(session, survivor.id)).blacklist_value == "user_id:222"


async def test_two_marked_records_leave_one_standing_mark(session, session_factory):
    """Слияние двух отмеченных оставляет одну действующую отметку.

    Второй строки с тем же написанием не допускает заведение, поэтому
    переезжающая гаснет, а действующей остаётся та, что уже стоит на
    написании выжившего. Погашенная видна на экране списка — решение не
    пропадает.
    """
    absorbed = hr_row(name="дубль", telegram_username="olga", telegram_user_id=222)
    survivor = hr_row(name="основной", telegram_username="maria", telegram_user_id=111)
    await put(session_factory, absorbed, survivor)
    await put(
        session_factory,
        blacklist_row("hr", "user_id:222"),
        blacklist_row("hr", "user_id:111"),
    )

    await merge_hr(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (await get_hr_detail(session, survivor.id)).blacklist_value == "user_id:111"
