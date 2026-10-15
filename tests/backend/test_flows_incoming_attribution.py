"""К какой вакансии бот относит письмо HR и что делает дальше.

У одного HR бывает несколько вакансий, и по тексту «да, давайте» не понять, о
какой он. Если HR ответил через ответ на конкретное наше сообщение — вакансия
известна точно: она записана у того сообщения. Без ответа берётся вакансия, о
которой мы этому человеку писали последней: разговор с ним начался с нашего
отклика.

Дальше письмо либо уходит в накопитель на отложенный разбор, либо разбирается
на месте. Вакансия, из состояния которой автоматика уже не двигает, до разбора
не доходит вовсе: он всё равно упёрся бы в ту же охрану, только за деньги.
"""

import logging
from datetime import timedelta, timezone

from backend.models import HR, Message, Vacancy, VacancyStatus
from backend.payloads import Classification, PendingReply
from backend.repository.messages import save_incoming_message
from backend.repository.vacancies_life import delete_vacancy
from tests.dbio import all_rows, only_row, put
from tests.factories import at, hr_row, message_row, vacancy_row
from tests.fakes.telegram_objects import TG_EPOCH, incoming, message, user


async def _two_vacancies(session_factory):
    """HR с двумя вакансиями, и о каждой мы ему писали — о «последней» позже.

    Письмо без цитаты относят к «последней». «Прежняя» лежит рядом затем,
    чтобы цитате было куда указать иначе, чем умолчанию: укажи обе на одну
    вакансию, и отбор по номеру письма прошёл бы молча.

    «Прежняя» при этом свежее по времени появления, хотя писали о ней
    раньше: так у человека и выходит — он публикует следующую вакансию,
    пока мы ждём ответа по предыдущей. Совпади «та, о которой писали
    последней» со «свежайшей у человека», набор одинаково устраивал бы и
    прежний, снятый отбор.
    """
    await put(session_factory, hr_row(telegram_user_id=777))
    hr = await only_row(session_factory, HR)
    await put(
        session_factory,
        vacancy_row(
            title="прежняя", hr_id=hr.id,
            status=VacancyStatus.APPLIED, created_at=at(-30),
        ),
        vacancy_row(
            title="последняя", hr_id=hr.id,
            status=VacancyStatus.APPLIED, created_at=at(-150),
        ),
    )
    by_title = {v.title: v for v in await all_rows(session_factory, Vacancy)}
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=by_title["последняя"].id,
            is_incoming=False, tg_message_id=101, sent_at=at(-60),
        ),
        message_row(
            hr_id=hr.id, vacancy_id=by_title["прежняя"].id,
            is_incoming=False, tg_message_id=100, sent_at=at(-120),
        ),
    )
    return hr, by_title


async def _one_vacancy(session_factory, *, title, status):
    """HR с одной вакансией, о которой мы ему уже писали.

    Наше письмо здесь не украшение: ответ без цитаты привязывают по нему.
    Без него письмо HR легло бы вовсе без вакансии — и до заслонов с
    разбором дело не дошло бы, а проверяют здесь именно их.
    """
    await put(session_factory, hr_row(telegram_user_id=777))
    hr = await only_row(session_factory, HR)
    await put(session_factory, vacancy_row(title=title, hr_id=hr.id, status=status))
    vacancy = await only_row(session_factory, Vacancy)
    await put(
        session_factory,
        message_row(
            hr_id=hr.id, vacancy_id=vacancy.id,
            is_incoming=False, tg_message_id=100, sent_at=at(-60),
        ),
    )
    return hr, vacancy


async def _their_letters(session_factory) -> list:
    """Письма HR из переписки: наши лежат там же, и читать надо не их."""
    return [m for m in await all_rows(session_factory, Message) if m.is_incoming]


def _ignore(*args):
    """Накопитель, которому всё равно.

    Подставляется там, где предмет проверки — привязка письма к вакансии:
    без накопителя разбор пошёл бы в языковую модель, а он тут ни при чём.
    """


async def test_a_reply_lands_on_the_vacancy_it_answers(session_factory, deliver):
    """Ответ на наше сообщение относится к вакансии того сообщения.

    Это единственный точный способ: у HR может быть пять вакансий, и по
    тексту «да, давайте» не понять, о которой он.
    """
    _, by_title = await _two_vacancies(session_factory)

    await deliver(
        incoming(text="да, давайте", reply_to_message_id=100), schedule=_ignore
    )

    saved = await _their_letters(session_factory)
    assert [m.vacancy_id for m in saved] == [by_title["прежняя"].id]


async def test_a_letter_without_a_reply_lands_on_what_we_wrote_about(
    session_factory, deliver
):
    """Письмо без цитаты относится к вакансии последнего нашего письма.

    Цепочку ответов HR соблюдает не каждый, а разговор с ним всё равно
    начался с нашего отклика — по нему он и отвечает.
    """
    _, by_title = await _two_vacancies(session_factory)

    await deliver(incoming(text="да, давайте"), schedule=_ignore)

    saved = await _their_letters(session_factory)
    assert [m.vacancy_id for m in saved] == [by_title["последняя"].id]


async def test_the_letter_time_is_read_in_our_scale(session_factory, deliver):
    """Время письма сверяют с нашими письмами, приведя к нашей же шкале.

    Отбор сравнивает его с колонками базы, а те наивные и по UTC. Метка от
    Telegram живёт по другим часам, и без приведения граница «на момент
    письма» уезжает на смещение пояса: ответ относят к вакансии, о которой
    в ту минуту ещё не написали.

    Метка взята с поясом нарочно: на машине, живущей по UTC, приведённая и
    сырая совпали бы, и проверка молчала бы вместе с бедой. Письмо помечено
    между двумя нашими, так что промах виден по тому, к какой вакансии его
    отнесли.
    """
    _, by_title = await _two_vacancies(session_factory)
    stamped = at(-90).replace(tzinfo=timezone.utc).astimezone(
        timezone(timedelta(hours=5))
    )

    await deliver(incoming(text="да, давайте", date=stamped), schedule=_ignore)

    saved = await _their_letters(session_factory)
    assert [m.vacancy_id for m in saved] == [by_title["прежняя"].id]


async def test_a_reply_to_something_unknown_falls_back_to_what_we_wrote_about(
    session_factory, deliver
):
    """Ответ на неизвестное сообщение относят к вакансии нашего письма.

    Переписка могла начаться до появления приложения — тогда нашей
    строки об исходном сообщении просто нет.
    """
    _, by_title = await _two_vacancies(session_factory)

    await deliver(
        incoming(text="да, давайте", reply_to_message_id=999), schedule=_ignore
    )

    saved = await _their_letters(session_factory)
    assert [m.vacancy_id for m in saved] == [by_title["последняя"].id]


async def test_a_letter_from_an_hr_we_never_wrote_to_lands_without_a_vacancy(
    session_factory, deliver
):
    """Письмо HR, которому мы не писали, ложится без вакансии.

    Вакансия у него при этом есть: ленту его канала бот разбирает и без
    нашего отклика. Сядь ответ на неё, разговор оказался бы привязан к
    строке, о которой мы не написали ни слова, — а ей чаще всего оказывается
    отклонённая, и до разбора письмо не дошло бы вовсе.
    """
    await put(session_factory, hr_row(telegram_user_id=777))
    hr = await only_row(session_factory, HR)
    await put(
        session_factory,
        vacancy_row(title="разобрана сама", hr_id=hr.id, status=VacancyStatus.NOT_FIT),
    )

    await deliver(incoming(text="да, давайте"), schedule=_ignore)

    saved = await _their_letters(session_factory)
    assert [m.vacancy_id for m in saved] == [None]


async def test_a_letter_from_an_hr_without_vacancies_is_still_saved(session_factory, deliver):
    """Письмо от HR без вакансий всё равно попадает в переписку.

    Пользователь мог завести карточку руками и написать первым; терять
    ответ из-за отсутствия вакансии значило бы прятать разговор.
    """
    await put(session_factory, hr_row(telegram_user_id=777))

    await deliver(incoming(text="да, давайте"))

    saved = await only_row(session_factory, Message)
    assert saved.vacancy_id is None
    assert saved.text == "да, давайте"


async def test_a_letter_is_handed_to_the_buffer_when_there_is_one(session_factory, deliver):
    """При наличии накопителя письмо уходит в него, а не разбирается сразу.

    Так собираются очереди: HR пишет тремя строками подряд, и разбор
    ждёт, пока он замолчит.

    Прежнее письмо в переписке лежит затем, чтобы номер строки не совпал с
    номером вакансии: совпади они, перестановка первых двух полей груза
    прошла бы молча — числа-то оба целые.
    """
    hr, by_title = await _two_vacancies(session_factory)
    await put(
        session_factory,
        message_row(hr_id=hr.id, is_incoming=True, tg_message_id=1, text="раньше"),
    )
    scheduled: list[tuple] = []

    await deliver(
        incoming(text="да, давайте"),
        schedule=lambda *args: scheduled.append(args),
    )

    saved = (await all_rows(session_factory, Message))[-1]
    assert saved.id != by_title["последняя"].id
    assert scheduled == [
        (
            hr.id,
            PendingReply(
                vacancy_id=by_title["последняя"].id,
                message_id=saved.id,
                tg_message_id=saved.tg_message_id,
                text="да, давайте",
            ),
        )
    ]


async def test_a_letter_about_a_new_vacancy_reaches_no_reader(
    session_factory, deliver
):
    """Письмо по вакансии, на которую мы ещё не откликались, не разбирают.

    Из «новой» автоматика ведёт ровно в «отклик отправлен», а отправляем его
    мы, не собеседник. Дай мы разбору выбирать из этих двух — письмо HR само
    объявляло бы отклик ушедшим, и кнопка отправки запиралась бы на вакансии,
    по которой мы не написали ни строки.
    """
    await _one_vacancy(
        session_factory, title="ещё не откликались", status=VacancyStatus.NEW
    )
    scheduled: list[tuple] = []

    await deliver(
        incoming(text="здравствуйте, вы откликались?"),
        schedule=lambda *args: scheduled.append(args),
    )

    assert scheduled == []
    saved = await _their_letters(session_factory)
    assert [m.text for m in saved] == ["здравствуйте, вы откликались?"]


async def test_a_vacancy_beyond_automation_reaches_no_reader(session_factory, deliver):
    """Письмо по вакансии, которую автоматика не двигает, не разбирают.

    Сообщение при этом сохраняется: оно след разговора, и терять его
    из-за статуса вакансии незачем.
    """
    await _one_vacancy(
        session_factory, title="отказали", status=VacancyStatus.DECLINE
    )
    scheduled: list[tuple] = []

    await deliver(
        incoming(text="да, давайте"),
        schedule=lambda *args: scheduled.append(args),
    )

    assert scheduled == []
    saved = await _their_letters(session_factory)
    assert [m.text for m in saved] == ["да, давайте"]


async def test_a_letter_about_a_vanished_vacancy_does_not_break_the_intake(
    session_factory, monkeypatch, deliver, caplog
):
    """Письмо по вакансии, удалённой пока оно шло, приём не роняет.

    Вакансию привязывают в одной сессии, а о её статусе спрашивают в
    следующей — в этот промежуток окно успевает её удалить. Изображено
    удалением из-под самой записи письма: внешние ключи не дают завести
    письмо со ссылкой на вакансию, которой уже нет, поэтому «пропала
    заранее» стендом не показать.

    Запись в журнале сверяется потому, что без неё «разбора не было»
    держалось бы на пустом клиенте модели в стенде, а не на заслоне.
    """
    _, vacancy = await _one_vacancy(
        session_factory, title="к отклику", status=VacancyStatus.APPLIED
    )

    async def save_and_lose_the_vacancy(session, incoming):
        saved = await save_incoming_message(session, incoming)
        await delete_vacancy(session, incoming.vacancy_id)
        return saved

    monkeypatch.setattr(
        "backend.flows.dm.save_incoming_message", save_and_lose_the_vacancy
    )

    with caplog.at_level(logging.INFO, logger="backend.flows.dm"):
        await deliver(incoming(text="да, давайте"), schedule=None)

    saved = await _their_letters(session_factory)
    assert [m.text for m in saved] == ["да, давайте"]
    assert await all_rows(session_factory, Vacancy) == []
    assert [
        rec.getMessage() for rec in caplog.records if rec.name == "backend.flows.dm"
    ] == [f"vacancy {vacancy.id}: status=gone closed for auto, skip classification"]


async def test_without_a_buffer_the_letter_is_read_on_the_spot(session_factory, monkeypatch, deliver):
    """Без накопителя письмо разбирается на месте.

    Этим путём идут догон пропущенного и запасной случай, когда
    планировщика не передали.
    """
    await _one_vacancy(
        session_factory, title="к отклику", status=VacancyStatus.APPLIED
    )
    asked: list[str] = []

    async def classify_hr_reply(ask, client, model):
        asked.append(ask.text)
        return (
            Classification(
                status=VacancyStatus.INVITATION, explanation="зовут на созвон"
            ),
            None,
        )

    monkeypatch.setattr("backend.flows.dm_classify.classify_hr_reply", classify_hr_reply)

    await deliver(incoming(text="да, давайте"), schedule=None)

    assert asked == ["да, давайте"]
    assert (
        await only_row(session_factory, Vacancy)
    ).status is VacancyStatus.INVITATION


async def test_a_reader_without_a_verdict_leaves_the_vacancy_alone(session_factory, monkeypatch, deliver):
    """Разбор без вердикта вакансию не двигает.

    Обращения к разборщику считаются здесь наравне со статусом: не спроси
    его вовсе — вакансия осталась бы на месте точно так же, и проверка
    молчала бы о письме, не дошедшем до разбора.
    """
    await _one_vacancy(
        session_factory, title="к отклику", status=VacancyStatus.APPLIED
    )
    asked: list[str] = []

    async def classify_hr_reply(ask, client, model):
        asked.append(ask.text)
        return None, None

    monkeypatch.setattr("backend.flows.dm_classify.classify_hr_reply", classify_hr_reply)

    await deliver(incoming(text="да, давайте"), schedule=None)

    assert asked == ["да, давайте"]
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED


async def test_the_quote_of_our_own_letter_does_not_go_to_the_reader(session_factory, deliver):
    """Цитата нашего же письма в разбор не уходит.

    В переписке ответ HR показывается вместе с цитатой того, на что он
    отвечает, — так читается разговор. Но разбирать эту цитату нельзя:
    в ней наш собственный текст, и модель приняла бы его за слова HR.
    """
    await _two_vacancies(session_factory)
    scheduled: list[tuple] = []
    quoted = message(
        id=10,
        text="да, давайте",
        date=TG_EPOCH,
        from_user=user(id=777, username=None),
        photo=None,
        document=None,
        reply_to_message_id=None,
        reply_to_message=message(text="Откликаюсь на вакансию", caption=None),
    )

    await deliver(quoted, schedule=lambda *a: scheduled.append(a))

    saved = await _their_letters(session_factory)
    assert saved[0].text.startswith("↪ Откликаюсь на вакансию")
    assert scheduled[0][1].text == "да, давайте"
