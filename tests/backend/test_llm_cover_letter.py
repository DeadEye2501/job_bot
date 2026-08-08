"""Следствия составления письма-отклика.

Письмо проходит два слоя проверки. Первый — детерминированный: не длиннее
подписи в Telegram, без оставшихся заготовок вроде «{роль}», не обрезанное на
полуслове, без упоминания вложений. Второй — сверка фактов с профилем у самой
модели.

Обращений к провайдеру за один вызов два, и ждут они разного: письмо
отклоняется, если содержит фигурную скобку, а вердикт проверки обязан быть
объектом. Поэтому ответы задаются очередью.
"""

import httpx
import pytest

from backend.llm import generate_cover_letter
from tests.factories import parsed_vacancy
from tests.fakes.llm import CHAT, chat_response, messages_of, provider

PASSES = '{"verdict": "ok", "issues": []}'


def _client(letter: str, *, finish_reason: str = "stop", factcheck: str = PASSES):
    """Провайдер, отвечающий сперва письмом, потом вердиктом проверки."""
    return provider(
        {
            CHAT: [
                chat_response(letter, finish_reason=finish_reason),
                chat_response(factcheck),
            ]
        }
    )


async def test_without_a_profile_nothing_is_asked_of_the_model():
    """Без сведений о кандидате к модели не обращаются вовсе."""
    client = provider({})

    got = await generate_cover_letter("", parsed_vacancy(), client, "qwen")

    assert got is None
    assert client.sent == []


async def test_a_good_letter_comes_back_as_it_was_written():
    """Годное письмо возвращается тем же текстом."""
    client = _client("Здравствуйте! Пишу по поводу вакансии.")

    got = await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")

    assert got == "Здравствуйте! Пишу по поводу вакансии."


async def test_the_vacancy_reaches_the_model_as_data():
    """Сведения о вакансии уходят модели отдельным блоком данных."""
    client = _client("Здравствуйте.")
    vacancy = parsed_vacancy(
        title="Ведущий питонист",
        company_name="Контур",
        stack_required=["Python"],
        salary="$3000",
    )

    await generate_cover_letter(
        "профиль", vacancy, client, "qwen", channel_ref="@pyjobs"
    )

    user = messages_of(client.sent[0])["user"]
    assert "Ведущий питонист" in user
    assert "Контур" in user
    assert "@pyjobs" in user
    assert "$3000" in user


async def test_an_unfilled_field_is_named_as_missing():
    """Незаполненное поле вакансии называется в блоке как «не указано»."""
    client = _client("Здравствуйте.")

    await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")

    assert "- Company: не указано" in messages_of(client.sent[0])["user"]


async def test_the_placeholders_of_the_prompt_are_filled_in():
    """Заготовки, оставленные промптом, заполняются до проверок.

    Проверка на оставшиеся заготовки идёт по фигурным скобкам, и не подставь
    мы свои — письмо отвергалось бы всегда.
    """
    client = _client("Здравствуйте! Пишу про {title} из {channel}.")

    got = await generate_cover_letter(
        "профиль",
        parsed_vacancy(title="Ведущий питонист"),
        client,
        "qwen",
        channel_ref="@pyjobs",
    )

    assert got == "Здравствуйте! Пишу про Ведущий питонист из @pyjobs."


async def test_brackets_inside_the_title_are_removed_before_substitution():
    """Скобки внутри названия вакансии убираются до подстановки.

    Название приходит от разбора, и «C++ Developer (template <T>)» после
    подстановки выглядело бы как оставшаяся заготовка — письмо отвергли бы
    ни за что.
    """
    client = _client("Здравствуйте, пишу про {title}.")

    got = await generate_cover_letter(
        "профиль",
        parsed_vacancy(title="C++ Developer (template <T>)"),
        client,
        "qwen",
    )

    assert got == "Здравствуйте, пишу про C++ Developer (template T)."


@pytest.mark.parametrize(
    "letter",
    [
        pytest.param("Здравствуйте, {роль} в {компания}.", id="фигурные скобки"),
        pytest.param("Здравствуйте, [должность] у вас.", id="квадратные скобки"),
        pytest.param("Здравствуйте, <роль> у вас.", id="угловые скобки"),
    ],
)
async def test_a_letter_with_a_leftover_placeholder_is_rejected(letter):
    """Письмо с оставшейся заготовкой не отправляется.

    Иначе HR получил бы в личку буквальное «{роль}».
    """
    client = _client(letter)

    assert (
        await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")
        is None
    )


async def test_an_arrow_is_not_mistaken_for_a_placeholder():
    """Стрелка и смайлик за заготовку не принимаются.

    Проверка по одному знаку «меньше» отвергала бы письма со стрелками и
    смайликами, поэтому ищется именно короткое слово в угловых скобках.
    """
    client = _client("Здравствуйте! Рос от джуна -> сеньора, всё честно.")

    got = await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")

    assert got is not None


async def test_a_letter_longer_than_the_caption_limit_is_rejected():
    """Письмо длиннее подписи к вложению не отправляется.

    Оно уходит подписью к резюме, и превышение предела Telegram обернулось
    бы отказом на его стороне.
    """
    client = _client("а" * 1025)

    assert (
        await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")
        is None
    )


async def test_a_letter_exactly_at_the_limit_is_sent():
    """Письмо ровно по пределу отправляется."""
    client = _client("а" * 1024)

    got = await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")

    assert got is not None


async def test_a_letter_cut_mid_sentence_is_rejected():
    """Письмо, оборванное на полуслове, не отправляется."""
    client = _client("Здравствуйте, я разрабо", finish_reason="length")

    assert (
        await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")
        is None
    )


async def test_a_letter_that_ended_in_time_is_sent_even_at_the_limit():
    """Письмо, успевшее закончиться, отправляется и при исчерпании места.

    Признак обрыва сам по себе не приговор: если последний знак —
    завершающий, письмо целое.
    """
    client = _client("Здравствуйте, я разработчик.", finish_reason="length")

    got = await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")

    assert got is not None


async def test_a_letter_mentioning_an_attachment_is_rejected():
    """Письмо, упоминающее вложение, не отправляется.

    Резюме и так уходит файлом, и фраза «прикладываю резюме» в подписи к
    нему выглядит нелепо.
    """
    client = _client("Здравствуйте! Прикладываю резюме, посмотрите.")

    assert (
        await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")
        is None
    )


async def test_an_empty_letter_is_rejected():
    """Пустое письмо не отправляется."""
    client = _client("   ")

    assert (
        await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")
        is None
    )


async def test_a_letter_rejected_by_the_factcheck_is_not_sent():
    """Письмо, отклонённое сверкой фактов, не отправляется."""
    client = _client(
        "Здравствуйте! Восемь лет пишу на Коболе.",
        factcheck='{"verdict": "reject", "issues": ["выдумал Кобол"]}',
    )

    assert (
        await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")
        is None
    )


async def test_the_factcheck_sees_the_letter_with_placeholders_filled_in():
    """Сверка фактов получает письмо уже с подставленными значениями.

    Иначе она увидела бы фигурные скобки и приняла настоящее название
    вакансии за выдуманный факт о кандидате.
    """
    client = _client("Здравствуйте, пишу про {title}.")

    await generate_cover_letter(
        "профиль", parsed_vacancy(title="Ведущий питонист"), client, "qwen"
    )

    second = messages_of(client.sent[1])["user"]
    assert "Ведущий питонист" in second
    assert "{title}" not in second


async def test_a_rejected_letter_never_reaches_the_factcheck():
    """Письмо, отвергнутое первым слоем, до сверки фактов не доходит.

    Тратить второе обращение к модели на заведомо негодный текст незачем.
    """
    client = _client("Здравствуйте, {роль}.")

    await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")

    assert len(client.sent) == 1


@pytest.mark.parametrize(
    "prepared",
    [
        pytest.param(httpx.Response(500, text="упал"), id="отказ провайдера"),
        pytest.param(httpx.ConnectError("сеть отвалилась"), id="обрыв связи"),
        pytest.param(httpx.Response(200, json={"нет": "выборов"}), id="чужая форма"),
    ],
)
async def test_trouble_with_the_first_call_yields_no_letter(prepared):
    """Беда с первым обращением письма не даёт и наружу не пробрасывается."""
    client = provider({CHAT: prepared})

    assert (
        await generate_cover_letter("профиль", parsed_vacancy(), client, "qwen")
        is None
    )
