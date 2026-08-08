"""Следствия отправки отклика кнопкой из карточки вакансии.

Отличие от автоматической в том, что решение принял пользователь: он смотрит
на карточку и жмёт кнопку. Поэтому отказы здесь называются понятнее — окно
показывает их подсказкой, — а сведения для письма собираются из уже
сохранённой строки, чтобы модель получила ту же форму запроса, что и при
обычном сборе.

Повторная отправка отбивается до всего остального: письмо уходит раньше, чем
переставляется статус, и «отправить ещё раз» означало бы второе настоящее
письмо тому же человеку.
"""

import pytest

from backend.models import HR, Vacancy, VacancyStatus
from tests.dbio import only_row, put
from tests.factories import hr_row, vacancy_row


@pytest.fixture
async def carded(make_pipeline, session_factory):
    """Конвейер и вакансия с привязанным HR — то, что видно в карточке."""
    await put(session_factory, hr_row())
    hr = await only_row(session_factory, HR)
    await put(
        session_factory,
        vacancy_row(
            title="Python-разработчик",
            description="Ищем в команду",
            company_name="Контур",
            hr_id=hr.id,
            status=VacancyStatus.NEW,
        ),
    )
    vacancy = await only_row(session_factory, Vacancy)

    pipeline = await make_pipeline()
    pipeline.asked = []

    async def send_application(hr_row_, parsed, vacancy_id, *, force=False):
        pipeline.asked.append((hr_row_.id, parsed, vacancy_id, force))
        return True, "sent"

    pipeline._send_application = send_application
    return pipeline, hr, vacancy


async def test_the_button_sends_the_application(carded):
    """Кнопка отправляет отклик и сообщает об успехе."""
    pipeline, hr, vacancy = carded

    assert await pipeline.send_application_for_vacancy(vacancy.id) == (True, "sent")
    assert [call[0] for call in pipeline.asked] == [hr.id]


async def test_the_send_is_marked_as_the_users_decision(carded):
    """Отправка помечается как решение пользователя, а не автоматики.

    Только с этой пометкой она перебивает защиту статуса — пользователь
    видит карточку и жмёт кнопку осознанно.
    """
    pipeline, hr, vacancy = carded

    await pipeline.send_application_for_vacancy(vacancy.id)

    assert pipeline.asked[0][3] is True


async def test_the_letter_is_written_from_the_saved_row(carded):
    """Сведения для письма собираются из сохранённой строки вакансии.

    Форма запроса к модели тогда та же, что при обычном сборе, и письмо
    не отличается от автоматического ничем, кроме повода.
    """
    pipeline, hr, vacancy = carded

    await pipeline.send_application_for_vacancy(vacancy.id)

    parsed = pipeline.asked[0][1]
    assert parsed.title == "Python-разработчик"
    assert parsed.description == "Ищем в команду"
    assert parsed.company_name == "Контур"


async def test_a_vanished_vacancy_is_named_in_the_refusal(carded):
    """Отказ по исчезнувшей вакансии называет причину."""
    pipeline, _, _ = carded

    assert await pipeline.send_application_for_vacancy(404) == (False, "no_vacancy")
    assert pipeline.asked == []


async def test_a_vacancy_without_an_hr_is_named_in_the_refusal(
    carded, session_factory
):
    """Отказ по вакансии без HR называет причину.

    Так бывает, когда разбор не нашёл в объявлении контакта: писать
    некому, и пользователю надо это сказать словами.
    """
    pipeline, _, vacancy = carded
    async with session_factory() as session:
        row = await session.get(Vacancy, vacancy.id)
        row.hr_id = None
        await session.commit()

    assert await pipeline.send_application_for_vacancy(vacancy.id) == (False, "no_hr")
    assert pipeline.asked == []


async def test_a_second_press_is_refused(carded, session_factory):
    """Повторное нажатие отбивается, а не шлёт второе письмо.

    Письмо уходит раньше, чем переставляется статус: пропустив это
    нажатие дальше, бот отправил бы HR настоящий второй отклик и только
    потом упёрся бы в защиту статуса.
    """
    pipeline, _, vacancy = carded
    async with session_factory() as session:
        row = await session.get(Vacancy, vacancy.id)
        row.status = VacancyStatus.APPLIED
        await session.commit()

    assert await pipeline.send_application_for_vacancy(vacancy.id) == (
        False,
        "already_applied",
    )
    assert pipeline.asked == []


async def test_a_refusal_from_the_sender_is_passed_through(carded):
    """Отказ, пришедший изнутри отправки, передаётся окну как есть.

    Причин там с полдесятка, и переводить их обратно в общее «не
    получилось» значило бы отнять у пользователя подсказку.
    """
    pipeline, _, vacancy = carded

    async def send_application(hr_row_, parsed, vacancy_id, *, force=False):
        return False, "cv_missing"

    pipeline._send_application = send_application

    assert await pipeline.send_application_for_vacancy(vacancy.id) == (
        False,
        "cv_missing",
    )


async def test_an_empty_profile_is_reloaded_before_the_send(carded):
    """Пустой блок сведений о кандидате перечитывается перед отправкой.

    Кнопку жмут из окна, а настройки читаются раз в цикл обхода: без
    перечитывания первая же ручная отправка после запуска упёрлась бы в
    «анкета пуста», хотя анкета заполнена.
    """
    pipeline, hr, vacancy = carded
    pipeline._profile_block = ""
    reloaded: list[int] = []

    async def reload():
        reloaded.append(1)
        pipeline._profile_block = "Иван Петров"

    pipeline._reload_resources = reload

    await pipeline.send_application_for_vacancy(vacancy.id)

    assert reloaded == [1]


async def test_a_filled_profile_is_not_reloaded(carded):
    """Заполненный блок сведений заново не читается.

    Перезагрузка обходит четыре таблицы; делать её на каждое нажатие
    незачем.
    """
    pipeline, hr, vacancy = carded
    pipeline._profile_block = "Иван Петров"
    reloaded: list[int] = []

    async def reload():
        reloaded.append(1)

    pipeline._reload_resources = reload

    await pipeline.send_application_for_vacancy(vacancy.id)

    assert reloaded == []
