"""Что именно уходит HR при отклике на вакансию.

Первый отклик за две недели — полное письмо с резюме. Второй и дальше —
короткая приписка без вложений и без обращения к модели: HR публикует по
несколько вакансий за раз, и получить от одного человека три одинаковых
простыни с резюме подряд неприятно ровно настолько, насколько это выглядит.

Каждый отказ назван своим словом. Окно показывает по нему подсказку, и общее
«не получилось» не дало бы пользователю понять, чинить ли анкету, файл резюме
или настройки.
"""

from backend.flows import apply
import pytest

from backend.models import HR, TelegramChannel, Vacancy, VacancyStatus
from tests.dbio import only_row, put
from tests.factories import (
    channel_row,
    days_ago,
    hr_row,
    message_row,
    parsed_vacancy,
    vacancy_row,
)


@pytest.fixture
async def applying(make_pipeline, session_factory, tmp_path, monkeypatch):
    """Конвейер, готовый отправить отклик: анкета, резюме и вакансия.

    Само письмо сочиняет модель; здесь она отдаёт заготовленный текст, а
    тест смотрит, что и с чем ушло.
    """
    resume = tmp_path / "Резюме.pdf"
    resume.write_bytes(b"%PDF")
    await put(session_factory, hr_row(), channel_row(username="pyjobs"))
    hr = await only_row(session_factory, HR)
    channel = await only_row(session_factory, TelegramChannel)
    await put(
        session_factory,
        vacancy_row(
            title="Python-разработчик",
            hr_id=hr.id,
            source_channel_id=channel.id,
            status=VacancyStatus.NEW,
        ),
    )
    vacancy = await only_row(session_factory, Vacancy)

    pipeline = await make_pipeline()
    await pipeline.rs.set_app("cv_path", str(resume))
    pipeline.profile_block = "Иван Петров, Python-разработчик"
    pipeline.letter = "Здравствуйте! Откликаюсь на вакансию."

    async def generate_cover_letter(block, parsed, client, model, *, channel_ref=None):
        pipeline.asked_for_letter = (block, parsed, channel_ref)
        return pipeline.letter

    monkeypatch.setattr("backend.flows.apply.generate_cover_letter", generate_cover_letter)
    return pipeline, hr, vacancy, resume


async def test_the_first_application_carries_the_letter_and_the_resume(applying):
    """Первый отклик уходит письмом от модели и с резюме."""
    pipeline, hr, vacancy, resume = applying

    ok, reason = await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id)

    assert (ok, reason) == (True, "sent")
    assert pipeline.sent == [
        (hr.id, "Здравствуйте! Откликаюсь на вакансию.", resume, vacancy.id, False)
    ]


async def test_the_letter_is_written_about_this_channel(applying):
    """Письмо сочиняется с оглядкой на канал, где вакансия найдена."""
    pipeline, hr, vacancy, _ = applying

    await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id)

    _, _, channel_ref = pipeline.asked_for_letter
    assert channel_ref == "@pyjobs"


async def test_a_second_application_is_short_and_carries_nothing(
    applying, session_factory
):
    """Второй отклик тому же HR — короткая приписка без вложений.

    Модель тут не зовут вовсе: письмо собирается по образцу, и это ещё и
    убирает задержку в несколько секунд на каждую следующую вакансию.
    """
    pipeline, hr, vacancy, _ = applying
    await put(
        session_factory,
        message_row(
            hr_id=hr.id,
            vacancy_id=vacancy.id,
            is_incoming=False,
            sent_at=days_ago(1),
        ),
    )
    pipeline.asked_for_letter = None

    ok, reason = await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id)

    assert (ok, reason) == (True, "sent")
    assert pipeline.asked_for_letter is None
    hr_id, text, attachment, vacancy_id, force = pipeline.sent[0]
    assert attachment is None
    assert text.startswith("А вот я увидел ещё одну интересную вакансию")


async def test_an_application_for_a_vanished_vacancy_says_so(applying):
    """Отклик по исчезнувшей вакансии называет причину отказа."""
    pipeline, hr, _, _ = applying

    assert await apply.send_application(pipeline, hr, parsed_vacancy(), 404) == (
        False,
        "no_vacancy",
    )


async def test_an_already_applied_vacancy_is_not_written_to_twice(
    applying, session_factory
):
    """Вакансия, по которой отклик уже ушёл, второго письма не получает.

    Ручная отправка и очередной цикл сходятся на одной вакансии; без
    этой проверки HR получил бы два письма подряд. Проверка стоит до
    сочинения письма: узнав об отказе после него, бот заплатил бы
    обращением к модели впустую.
    """
    pipeline, hr, vacancy, _ = applying
    async with session_factory() as session:
        row = await session.get(Vacancy, vacancy.id)
        row.status = VacancyStatus.APPLIED
        await session.commit()

    pipeline.asked_for_letter = None

    assert await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id) == (
        False,
        "race",
    )
    assert pipeline.sent == []
    assert pipeline.asked_for_letter is None


async def test_a_manual_application_overrides_the_race_guard(
    applying, session_factory
):
    """Отправка из окна проверку «уже откликались» перебивает.

    Пользователь видит карточку и жмёт кнопку осознанно: защита стережёт
    автоматику, а не его решение.
    """
    pipeline, hr, vacancy, _ = applying
    async with session_factory() as session:
        row = await session.get(Vacancy, vacancy.id)
        row.status = VacancyStatus.APPLIED
        await session.commit()

    ok, reason = await apply.send_application(pipeline, 
        hr, parsed_vacancy(), vacancy.id, force=True
    )

    assert (ok, reason) == (True, "sent")


async def test_an_empty_profile_stops_the_full_letter(applying):
    """Без заполненной анкеты полное письмо не уходит.

    Писать HR от лица пустого профиля хуже, чем не писать вовсе.
    """
    pipeline, hr, vacancy, _ = applying
    pipeline.profile_block = ""

    assert await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id) == (
        False,
        "profile_empty",
    )
    assert pipeline.sent == []


async def test_a_letter_the_model_did_not_write_stops_the_send(applying):
    """Ненаписанное письмо отправку останавливает, а не заменяется заглушкой."""
    pipeline, hr, vacancy, _ = applying
    pipeline.letter = None

    assert await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id) == (
        False,
        "cover_letter_failed",
    )
    assert pipeline.sent == []


async def test_a_missing_resume_stops_the_full_letter(applying, session_factory):
    """Без файла резюме полное письмо не уходит.

    Первый отклик без вложения выглядит как обрывок; лучше сказать
    пользователю, что файл не найден.
    """
    pipeline, hr, vacancy, resume = applying
    resume.unlink()

    assert await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id) == (
        False,
        "cv_missing",
    )
    assert pipeline.sent == []


async def test_a_resume_that_vanished_at_the_last_moment_says_so(applying):
    """Резюме, пропавшее в последний миг, названо своей причиной.

    Между проверкой файла и его чтением проходит время, и пользователь
    успевает его переместить.
    """
    pipeline, hr, vacancy, resume = applying

    async def send(hr_row, text, attachment=None, vacancy_id=None, *, force=False):
        raise FileNotFoundError(str(resume))

    pipeline.send = send

    assert await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id) == (
        False,
        "cv_missing",
    )


async def test_a_refused_send_is_named_blocked(applying):
    """Отправку, которую отбил сам бот, называют запретом.

    Так бывает при выключенном режиме, чёрном списке и HR без адреса —
    причину в каждом случае бот уже записал в журнал.
    """
    pipeline, hr, vacancy, _ = applying

    async def send(hr_row, text, attachment=None, vacancy_id=None, *, force=False):
        return False

    pipeline.send = send

    assert await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id) == (
        False,
        "blocked",
    )


async def test_a_broken_send_is_named_a_telegram_error(applying):
    """Сорвавшуюся отправку называют ошибкой Telegram, а не молчат.

    Окно показывает по этому коду подсказку; проглотив сбой, оно сказало
    бы пользователю, что отклик ушёл.
    """
    pipeline, hr, vacancy, _ = applying

    async def send(hr_row, text, attachment=None, vacancy_id=None, *, force=False):
        raise OSError("сеть")

    pipeline.send = send

    assert await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id) == (
        False,
        "telegram_error",
    )


async def test_a_vacancy_without_a_title_is_still_written_about(
    applying, session_factory
):
    """Вакансия без названия отклик не отменяет.

    Название берётся из разбора и иногда не выходит; отменять из-за него
    сделанное дело значило бы менять его на подпись.
    """
    pipeline, hr, vacancy, _ = applying
    async with session_factory() as session:
        row = await session.get(Vacancy, vacancy.id)
        row.title = None
        await session.commit()
    await put(
        session_factory,
        message_row(
            hr_id=hr.id,
            vacancy_id=vacancy.id,
            is_incoming=False,
            sent_at=days_ago(1),
        ),
    )

    ok, reason = await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id)

    assert (ok, reason) == (True, "sent")
    assert "вашу вакансию" in pipeline.sent[0][1]


async def test_a_rate_limit_window_holds_the_auto_send(applying):
    """Пока окно запрета не вышло, автоматика не отправляет.

    Стучаться раньше срока — верный способ получить запрет подольше.
    """
    import time

    pipeline, hr, vacancy, _ = applying
    await pipeline.rs.set_app("flood_wait_until_ts", str(time.time() + 999))

    assert await apply.try_auto_send(pipeline, hr, parsed_vacancy(), vacancy.id) == (
        False,
        "flood_wait",
    )
    assert pipeline.sent == []


async def test_an_expired_rate_limit_window_lets_the_send_through(applying):
    """Истёкшее окно запрета отправку больше не держит."""
    import time

    pipeline, hr, vacancy, _ = applying
    await pipeline.rs.set_app("flood_wait_until_ts", str(time.time() - 10))

    ok, reason = await apply.try_auto_send(pipeline, hr, parsed_vacancy(), vacancy.id)

    assert (ok, reason) == (True, "sent")


async def test_a_second_send_while_the_first_is_in_flight_is_refused(
    applying, monkeypatch
):
    """Пока письмо сочиняется, вторая отправка по той же вакансии отбивается.

    Заслон «уже откликались» её не ловит: он смотрит на статус, а статус
    меняется в самом конце, когда письмо уже ушло. Всё это время нажатие в
    окне заводило бы вторую отправку, и HR получал бы два письма подряд.
    """
    pipeline, hr, vacancy, _ = applying
    second: list[tuple] = []

    async def generate_cover_letter(block, parsed, client, model, *, channel_ref=None):
        second.append(
            await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id)
        )
        return pipeline.letter

    monkeypatch.setattr(
        "backend.flows.apply.generate_cover_letter", generate_cover_letter
    )

    ok, reason = await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id)

    assert (ok, reason) == (True, "sent")
    assert second == [(False, "in_flight")]
    assert len(pipeline.sent) == 1


async def test_a_send_that_finished_lets_the_next_one_through(applying):
    """Кончившаяся отправка заслон снимает: следующая идёт своим ходом."""
    pipeline, hr, vacancy, _ = applying

    await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id)
    ok, reason = await apply.send_application(
        pipeline, hr, parsed_vacancy(), vacancy.id
    )

    assert (ok, reason) == (True, "sent")


async def test_a_send_that_broke_lets_the_next_one_through_too(applying, monkeypatch):
    """Сорвавшаяся отправка заслон снимает тоже.

    Иначе одна беда посреди сочинения письма запирала бы вакансию от новых
    попыток до перезапуска приложения.
    """
    pipeline, hr, vacancy, _ = applying

    tries = []

    async def breaks_once(block, parsed, client, model, *, channel_ref=None):
        tries.append(1)
        if len(tries) == 1:
            raise RuntimeError("модель отвалилась")
        return pipeline.letter

    monkeypatch.setattr("backend.flows.apply.generate_cover_letter", breaks_once)
    with pytest.raises(RuntimeError):
        await apply.send_application(pipeline, hr, parsed_vacancy(), vacancy.id)

    ok, reason = await apply.send_application(
        pipeline, hr, parsed_vacancy(), vacancy.id
    )

    assert (ok, reason) == (True, "sent")
