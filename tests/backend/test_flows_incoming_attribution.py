"""К какой вакансии бот относит письмо HR и что делает дальше.

У одного HR бывает несколько вакансий, и по тексту «да, давайте» не понять, о
какой он. Если HR ответил через ответ на конкретное наше сообщение — вакансия
известна точно: она записана у того сообщения. Без ответа берётся самая свежая
вакансия этого HR на момент письма — приближение, но для одного HR с одной
вакансией оно верное всегда.

Дальше письмо либо уходит в накопитель на отложенный разбор, либо разбирается
на месте. Вакансия, из состояния которой автоматика уже не двигает, до разбора
не доходит вовсе: он всё равно упёрся бы в ту же охрану, только за деньги.
"""

from backend.flows import process_dm
from backend.models import HR, Message, Vacancy, VacancyStatus
from backend.payloads import Classification
from tests.dbio import all_rows, only_row, put
from tests.factories import at, hr_row, message_row, vacancy_row
from tests.fakes.telegram import SENT_AT, message, user


def _incoming(*, msg_id=10, reply_to=None):
    """Входящее письмо от собеседника, возможно ответом на наше."""
    return message(
        id=msg_id,
        text="да, давайте",
        date=SENT_AT,
        from_user=user(id=777, username=None),
        photo=None,
        document=None,
        reply_to_message_id=reply_to,
    )


async def _two_vacancies(session_factory):
    """HR с двумя вакансиями: старой и свежей.

    Свежая заводится первой, чтобы порядок вставки не совпал с
    ожидаемым: иначе «самую свежую» нельзя было бы отличить от
    «последней записанной».
    """
    await put(session_factory, hr_row(telegram_user_id=777))
    hr = await only_row(session_factory, HR)
    await put(
        session_factory,
        vacancy_row(
            title="свежая",
            hr_id=hr.id,
            status=VacancyStatus.APPLIED,
            created_at=at(-60),
        ),
        vacancy_row(
            title="старая",
            hr_id=hr.id,
            status=VacancyStatus.APPLIED,
            created_at=at(-120),
        ),
    )
    by_title = {v.title: v for v in await all_rows(session_factory, Vacancy)}
    return hr, by_title


def _ignore(*args):
    """Накопитель, которому всё равно: разбор дальше не идёт."""


async def _deliver(session_factory, msg, schedule=_ignore):
    """Проводит письмо через разбор входящего.

    По умолчанию накопитель подставлен пустой: тесту про то, к какой
    вакансии отнесли письмо, разбор уже не нужен, а без накопителя он
    пошёл бы в языковую модель.
    """
    await process_dm(
        msg, None, "qwen", session_factory, schedule_classification=schedule
    )


async def test_a_reply_lands_on_the_vacancy_it_answers(session_factory):
    """Ответ на наше сообщение относится к вакансии того сообщения.

    Это единственный точный способ: у HR может быть пять вакансий, и по
    тексту «да, давайте» не понять, о которой он.
    """
    hr, by_title = await _two_vacancies(session_factory)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id,
            vacancy_id=by_title["старая"].id,
            is_incoming=False,
            tg_message_id=100,
        ),
    )

    await _deliver(session_factory, _incoming(reply_to=100))

    saved = [m for m in await all_rows(session_factory, Message) if m.is_incoming]
    assert [m.vacancy_id for m in saved] == [by_title["старая"].id]


async def test_a_letter_without_a_reply_lands_on_the_freshest(session_factory):
    """Письмо без ответа относится к самой свежей вакансии этого HR.

    Приближение, но для одного HR с одной вакансией верное всегда, а
    цепочку ответов HR соблюдает не каждый.
    """
    hr, by_title = await _two_vacancies(session_factory)

    await _deliver(session_factory, _incoming())

    assert (await only_row(session_factory, Message)).vacancy_id == by_title["свежая"].id


async def test_a_reply_to_something_unknown_falls_back_to_the_freshest(
    session_factory
):
    """Ответ на неизвестное сообщение относят к самой свежей вакансии.

    Переписка могла начаться до появления приложения — тогда нашей
    строки об исходном сообщении просто нет.
    """
    hr, by_title = await _two_vacancies(session_factory)

    await _deliver(session_factory, _incoming(reply_to=999))

    assert (await only_row(session_factory, Message)).vacancy_id == by_title["свежая"].id


async def test_a_letter_from_an_hr_without_vacancies_is_still_saved(session_factory):
    """Письмо от HR без вакансий всё равно попадает в переписку.

    Пользователь мог завести карточку руками и написать первым; терять
    ответ из-за отсутствия вакансии значило бы прятать разговор.
    """
    await put(session_factory, hr_row(telegram_user_id=777))

    await _deliver(session_factory, _incoming())

    saved = await only_row(session_factory, Message)
    assert saved.vacancy_id is None
    assert saved.text == "да, давайте"


async def test_a_letter_is_handed_to_the_buffer_when_there_is_one(session_factory):
    """При наличии накопителя письмо уходит в него, а не разбирается сразу.

    Так собираются очереди: HR пишет тремя строками подряд, и разбор
    ждёт, пока он замолчит.
    """
    hr, by_title = await _two_vacancies(session_factory)
    scheduled: list[tuple] = []

    await _deliver(
        session_factory,
        _incoming(),
        schedule=lambda *args: scheduled.append(args),
    )

    saved = await only_row(session_factory, Message)
    assert scheduled == [(hr.id, by_title["свежая"].id, saved.id, "да, давайте")]


async def test_a_vacancy_beyond_automation_reaches_no_reader(session_factory):
    """Письмо по вакансии, которую автоматика не двигает, не разбирают.

    Сообщение при этом сохраняется: оно след разговора, и терять его
    из-за статуса вакансии незачем.
    """
    await put(
        session_factory,
        hr_row(telegram_user_id=777),
    )
    hr = await only_row(session_factory, HR)
    await put(
        session_factory,
        vacancy_row(
            title="отказали",
            hr_id=hr.id,
            status=VacancyStatus.DECLINE,
            created_at=at(-60),
        ),
    )
    scheduled: list[tuple] = []

    await _deliver(
        session_factory,
        _incoming(),
        schedule=lambda *args: scheduled.append(args),
    )

    assert scheduled == []
    assert (await only_row(session_factory, Message)).text == "да, давайте"


async def test_without_a_buffer_the_letter_is_read_on_the_spot(
    session_factory, monkeypatch
):
    """Без накопителя письмо разбирается на месте.

    Этим путём идут догон пропущенного и запасной случай, когда
    планировщика не передали.
    """
    await put(
        session_factory,
        hr_row(telegram_user_id=777),
    )
    hr = await only_row(session_factory, HR)
    await put(
        session_factory,
        vacancy_row(
            title="к отклику",
            hr_id=hr.id,
            status=VacancyStatus.APPLIED,
            created_at=at(-60),
        ),
    )
    asked: list[str] = []

    async def classify_hr_reply(text, status, client, model):
        asked.append(text)
        return Classification(
            status=VacancyStatus.INVITATION, explanation="зовут на созвон"
        )

    monkeypatch.setattr("backend.flows.classify_hr_reply", classify_hr_reply)

    await _deliver(session_factory, _incoming(), schedule=None)

    assert asked == ["да, давайте"]
    assert (
        await only_row(session_factory, Vacancy)
    ).status is VacancyStatus.INVITATION


async def test_a_reader_without_a_verdict_leaves_the_vacancy_alone(
    session_factory, monkeypatch
):
    """Разбор без вердикта вакансию не двигает."""
    await put(
        session_factory,
        hr_row(telegram_user_id=777),
    )
    hr = await only_row(session_factory, HR)
    await put(
        session_factory,
        vacancy_row(
            title="к отклику",
            hr_id=hr.id,
            status=VacancyStatus.APPLIED,
            created_at=at(-60),
        ),
    )

    async def classify_hr_reply(text, status, client, model):
        return None

    monkeypatch.setattr("backend.flows.classify_hr_reply", classify_hr_reply)

    await _deliver(session_factory, _incoming(), schedule=None)

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED
