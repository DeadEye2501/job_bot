"""Следствия разбора накопленного ответа HR.

Пакет уходит в модель одним куском, а решение по нему применяется к вакансии,
к которой относилось последнее сообщение. Перед обращением к модели ещё раз
смотрят на две вещи, изменившиеся за минуту ожидания: не попал ли HR в чёрный
список и не ушла ли вакансия в состояние, из которого автоматика её не
двигает. Обе проверки экономят обращение, которое всё равно ни к чему бы не
привело.

Сообщения склеиваются двойным переводом строки нарочно: модель должна видеть
границы между ними и выбрать самый продвинутый сигнал по всему пакету, а не
по последней фразе.
"""

import pytest

from backend.models import HR, Message, Vacancy, VacancyStatus, VacancyStatusHistory
from backend.payloads import Classification
from tests.dbio import all_rows, only_row, put
from tests.factories import blacklist_row, hr_row, message_row, vacancy_row


@pytest.fixture
async def reading(make_pipeline, session_factory, monkeypatch):
    """Конвейер, сохранённые HR с вакансией и подставной разбор ответа.

    Настоящий разбор ходит в языковую модель; здесь он отдаёт заготовленный
    вердикт и записывает, с каким текстом и статусом его позвали.
    """
    await put(
        session_factory,
        hr_row(),
        vacancy_row(title="к отклику", status=VacancyStatus.APPLIED),
    )
    hr = await only_row(session_factory, HR)
    vacancy = await only_row(session_factory, Vacancy)
    await put(
        session_factory,
        message_row(hr_id=hr.id, vacancy_id=vacancy.id, is_incoming=True),
    )
    message = await only_row(session_factory, Message)

    pipeline = await make_pipeline()
    pipeline.asked = []
    pipeline.verdict = Classification(
        status=VacancyStatus.INVITATION, explanation="зовут на созвон"
    )

    async def classify_hr_reply(text, status, client, model):
        pipeline.asked.append((text, status))
        if isinstance(pipeline.verdict, Exception):
            raise pipeline.verdict
        return pipeline.verdict

    monkeypatch.setattr("backend.flows.classify_hr_reply", classify_hr_reply)
    return pipeline, hr, vacancy, message


def _buffer(pipeline, hr, vacancy, message, *texts):
    """Кладёт в накопитель пакет от собеседника."""
    pipeline._dm_classify_buffer[hr.id] = [
        {"vacancy_id": vacancy.id, "msg_id": message.id, "text": text}
        for text in texts
    ]


async def test_the_whole_burst_goes_to_the_model_at_once(reading):
    """В модель уходит весь пакет разом, с границами между сообщениями.

    Двойной перевод строки — и есть граница: по ней модель отличает
    отдельные реплики и выбирает самый продвинутый сигнал по всему
    пакету, а не по последней фразе.
    """
    pipeline, hr, vacancy, message = reading
    _buffer(pipeline, hr, vacancy, message, "привет", "давайте созвонимся")

    await pipeline._classify_and_apply_for_hr(hr.id)

    assert pipeline.asked == [
        ("привет\n\nдавайте созвонимся", VacancyStatus.APPLIED),
    ]


async def test_the_verdict_moves_the_vacancy(reading, session_factory):
    """Вердикт модели переводит вакансию и попадает в её историю."""
    pipeline, hr, vacancy, message = reading
    _buffer(pipeline, hr, vacancy, message, "давайте созвонимся")

    await pipeline._classify_and_apply_for_hr(hr.id)

    assert (
        await only_row(session_factory, Vacancy)
    ).status is VacancyStatus.INVITATION
    step = await only_row(session_factory, VacancyStatusHistory)
    assert step.previous_status is VacancyStatus.APPLIED
    assert step.status is VacancyStatus.INVITATION
    assert step.explanation.startswith("зовут на созвон")


async def test_the_buffer_is_emptied_by_the_reading(reading):
    """Разбор опустошает накопитель: тот же пакет второй раз не разбирают."""
    pipeline, hr, vacancy, message = reading
    _buffer(pipeline, hr, vacancy, message, "давайте созвонимся")

    await pipeline._classify_and_apply_for_hr(hr.id)

    assert hr.id not in pipeline._dm_classify_buffer


async def test_an_empty_buffer_asks_the_model_nothing(reading):
    """Пустой накопитель до модели не доходит."""
    pipeline, hr, _, _ = reading

    await pipeline._classify_and_apply_for_hr(hr.id)

    assert pipeline.asked == []


async def test_a_blacklisted_hr_is_not_read_at_all(reading, session_factory):
    """Пакет от HR, попавшего в чёрный список, не разбирают.

    Список могли взвести за ту самую минуту ожидания: во входящий фильтр
    он тогда не попал, а разбирать его уже незачем.
    """
    pipeline, hr, vacancy, message = reading
    await put(session_factory, blacklist_row("hr", "@maria"))
    _buffer(pipeline, hr, vacancy, message, "давайте созвонимся")

    await pipeline._classify_and_apply_for_hr(hr.id)

    assert pipeline.asked == []
    assert hr.id not in pipeline._dm_classify_buffer
    assert (
        await only_row(session_factory, Vacancy)
    ).status is VacancyStatus.APPLIED


async def test_a_vacancy_beyond_automation_is_not_read_either(
    reading, session_factory
):
    """Пакет по вакансии, которую автоматика больше не двигает, не разбирают.

    Пользователь мог сам выставить отказ за время ожидания. Обращение к
    модели всё равно уперлось бы в ту же охрану статуса — только позже и
    за деньги.
    """
    pipeline, hr, vacancy, message = reading
    async with session_factory() as session:
        row = await session.get(Vacancy, vacancy.id)
        row.status = VacancyStatus.DECLINE
        await session.commit()
    _buffer(pipeline, hr, vacancy, message, "давайте созвонимся")

    await pipeline._classify_and_apply_for_hr(hr.id)

    assert pipeline.asked == []
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.DECLINE


async def test_a_model_that_gave_no_verdict_changes_nothing(
    reading, session_factory
):
    """Модель без вердикта вакансию не двигает.

    Она отвечает пустотой на болтовню не по делу; переводить статус
    по «спасибо, посмотрим» было бы выдумкой.
    """
    pipeline, hr, vacancy, message = reading
    pipeline.verdict = None
    _buffer(pipeline, hr, vacancy, message, "спасибо, посмотрим")

    await pipeline._classify_and_apply_for_hr(hr.id)

    assert (
        await only_row(session_factory, Vacancy)
    ).status is VacancyStatus.APPLIED
    assert await all_rows(session_factory, VacancyStatusHistory) == []


async def test_a_broken_model_call_changes_nothing(reading, session_factory):
    """Сорвавшееся обращение к модели вакансию не двигает и не роняет бота.

    Модель работает на машине пользователя и отваливается обычным делом;
    ронять из-за неё разбор входящих значило бы терять и переписку.
    """
    pipeline, hr, vacancy, message = reading
    pipeline.verdict = RuntimeError("модель не ответила")
    _buffer(pipeline, hr, vacancy, message, "давайте созвонимся")

    await pipeline._classify_and_apply_for_hr(hr.id)

    assert (
        await only_row(session_factory, Vacancy)
    ).status is VacancyStatus.APPLIED


async def test_the_window_hears_about_the_moved_vacancy(reading):
    """Окно узнаёт о переехавшей вакансии: список обновится сразу."""
    pipeline, hr, vacancy, message = reading
    heard: list[int] = []
    pipeline.on_vacancies_changed = lambda: heard.append(1)
    _buffer(pipeline, hr, vacancy, message, "давайте созвонимся")

    await pipeline._classify_and_apply_for_hr(hr.id)

    assert heard == [1]


async def test_a_broken_window_hook_does_not_undo_the_move(
    reading, session_factory
):
    """Сломанное оповещение окна перевод вакансии не отменяет."""
    pipeline, hr, vacancy, message = reading

    def broken():
        raise RuntimeError("окно")

    pipeline.on_vacancies_changed = broken
    _buffer(pipeline, hr, vacancy, message, "давайте созвонимся")

    await pipeline._classify_and_apply_for_hr(hr.id)

    assert (
        await only_row(session_factory, Vacancy)
    ).status is VacancyStatus.INVITATION


async def test_the_verdict_lands_on_the_vacancy_of_the_last_message(
    reading, session_factory
):
    """Решение относят к вакансии последнего сообщения пакета.

    HR за минуту успевает написать про две вакансии подряд; относить
    вердикт к первой значило бы двигать не ту.
    """
    pipeline, hr, vacancy, message_row_ = reading
    await put(
        session_factory,
        vacancy_row(title="вторая", status=VacancyStatus.APPLIED),
    )
    second = next(
        v for v in await all_rows(session_factory, Vacancy) if v.title == "вторая"
    )
    pipeline._dm_classify_buffer[hr.id] = [
        {"vacancy_id": vacancy.id, "msg_id": message_row_.id, "text": "про первую"},
        {"vacancy_id": second.id, "msg_id": message_row_.id, "text": "и про вторую"},
    ]

    await pipeline._classify_and_apply_for_hr(hr.id)

    by_title = {v.title: v for v in await all_rows(session_factory, Vacancy)}
    assert by_title["вторая"].status is VacancyStatus.INVITATION
    assert by_title["к отклику"].status is VacancyStatus.APPLIED
