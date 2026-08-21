"""Обстановка для проверок конвейера: он собран на подделках, модель молчит."""

import asyncio
from contextlib import suppress

import pytest

from backend.flows import apply, dm_classify
from backend.flows.dm import DmHelpers, process_dm
from backend.flows.pipeline import IngestionPipeline, LmProviders
from backend.models import (
    Profile,
    Vacancy,
    VacancyStatus,
)
from backend.payloads import FitValidation, PostGenre
from backend.runtime_settings import RuntimeSettings
from tests.dbio import only_row, put
from tests.factories import (
    parsed_vacancy,
    profile_row,
    profile_skill_row,
    vacancy_row,
)
from tests.fakes.lm_studio import LmClient
from tests.fakes.telegram import FakeTelegramClient, photo, user


def known_hr_client() -> FakeTelegramClient:
    """Подделка Telegram, знающая одного HR — с картинкой профиля."""
    return FakeTelegramClient(
        users={
            "maria": user(
                id=777,
                username="maria",
                first_name="Мария",
                photo=photo(small_file_id="кар"),
            )
        },
        avatar=b"\x89PNG",
    )


def _pipeline_on_fakes(session_factory, client, settings) -> IngestionPipeline:
    """Конвейер на подделках; отправку письма подменяет список `sent`."""
    outgoing: list[tuple] = []

    async def send(hr, text, attachment=None, vacancy_id=None, *, force=False):
        outgoing.append((hr.id, text, attachment, vacancy_id, force))
        return True

    pipeline = IngestionPipeline(
        client=client,
        session_factory=session_factory,
        models=LmProviders(
            chat_client=LmClient("http://provider.test"),
            chat_model="qwen",
            embed_client=LmClient("http://provider.test"),
            embed_model="bge",
        ),
        send=send,
        runtime_settings=settings,
    )
    pipeline.sent = outgoing
    return pipeline


async def _put_out_backfills(pipelines) -> None:
    """Гасит фоновые догоны переписки, заведённые за время теста.

    Разбор вакансии заводит их сам при появлении нового HR. Брошенная
    задача жалуется в поток ошибок при сборке мусора, и жалоба всплывает
    посреди чужого прогона.
    """
    for pipeline in pipelines:
        for task in list(pipeline.backfill_tasks):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def _answer_instead_of_the_model(pipeline, monkeypatch) -> None:
    """Подменяет разбор, проверку пригодности и отправку заготовленным."""

    async def parse_vacancy(text, client_, model, **kwargs):
        pipeline.parse_asked = True
        return pipeline.parsed, pipeline.parse_refusal

    async def classify_post_genre(text, client_, model):
        pipeline.genre_asked = True
        return pipeline.genre, pipeline.genre_trouble

    def asking_fit(about: str):
        """Один из трёх зовов о пригодности, называющий себя в общем следе.

        Ответ по умолчанию у всех троих один и тот же: предмет большинства
        проверок — порядок зовов, а не то, кто из троих вынес отказ. Тому,
        кому нужен ответ именно от второго или третьего, служит `verdict_by`.
        """

        async def ask(parsed, text, client_, model, **kwargs):
            pipeline.validated = True
            pipeline.fit_asked.append(about)
            return pipeline.verdict_by.get(about, pipeline.verdict), pipeline.fit_trouble

        return ask

    async def try_auto_send(pipeline, hr, parsed, vacancy_id):
        pipeline.asked_to_send.append(vacancy_id)
        return True, "sent"

    monkeypatch.setattr(apply, "try_auto_send", try_auto_send)
    monkeypatch.setattr("backend.flows.parse.parse_vacancy", parse_vacancy)
    monkeypatch.setattr("backend.flows.parse.classify_post_genre", classify_post_genre)
    monkeypatch.setattr("backend.flows.parse.validate_role_fit", asking_fit("роль"))
    monkeypatch.setattr(
        "backend.flows.parse.validate_language_fit", asking_fit("языки")
    )
    monkeypatch.setattr(
        "backend.flows.parse.validate_preferences_fit", asking_fit("предпочтения")
    )


@pytest.fixture
async def make_pipeline(session_factory):
    """Собирает `IngestionPipeline` на подделках вместо живых соединений.

    Настоящий конвейер держит клиента Pyrogram и два клиента httpx.
    Отдельно от `make_bot` он нужен потому, что проверяется сам конвейер, а
    не бот вокруг него: собирать ради него бота значило бы тащить в тест
    обработчики, цикл и настройки, к делу не относящиеся.

    Отправка письма подменяется списком: конвейер зовёт её как обычную
    сопрограмму, а тест смотрит, что и кому ушло.
    """
    built: list = []

    async def build(client=None):
        settings = await RuntimeSettings.load(session_factory)
        pipeline = _pipeline_on_fakes(
            session_factory, client or FakeTelegramClient(), settings
        )
        built.append(pipeline)
        return pipeline

    yield build

    await _put_out_backfills(built)


@pytest.fixture
def deliver(session_factory):
    """Проводит письмо через разбор входящего.

    Нужен двум слайсам — «кого слушают» и «к какой вакансии относят», — и
    оба зовут одно и то же с разными подменами: клиентом Telegram и
    накопителем отложенного разбора.
    """

    async def run(msg, *, client=None, schedule=None):
        return await process_dm(
            msg,
            DmHelpers(
                session_factory=session_factory,
                lm_chat_model="qwen",
                client=client,
                schedule_classification=schedule,
            ),
        )

    return run


@pytest.fixture
async def unparsed_vacancy(session_factory):
    """Неразобранная вакансия с чужим приговором.

    Приговор именно чужой: с умолчаниями «осталась новой» проверка была бы
    верна и до разбора, то есть не стерегла бы ничего.
    """
    await put(
        session_factory,
        vacancy_row(
            title=None,
            is_parsed=False,
            raw_text="текст",
            status=VacancyStatus.NOT_FIT,
            skip_reason="прошлый отказ",
        ),
    )
    return await only_row(session_factory, Vacancy)


def _fit_answers_by_default(pipeline) -> None:
    """Заготовленные ответы трёх зовов о пригодности и след того, кого спросили.

    Своим объявлением, а не строками фикстуры: зовов три, у каждого свой
    заготовленный ответ и общий на всех след, и вместе это половина настройки
    конвейера.
    """
    pipeline.verdict = FitValidation(verdict="fit", reason="ищем в команду")
    # Причина, по которой вердикт не спросился: пусто — спросили и получили.
    pipeline.fit_trouble = None
    pipeline.validated = False
    # Кого из троих спросили и в каком порядке: отказ прекращает остальные, и
    # увидеть это можно только следом зовов.
    pipeline.fit_asked = []
    # Ответ отдельного зова, если тесту нужен именно он; остальные отвечают
    # общим `verdict`.
    pipeline.verdict_by = {}


@pytest.fixture
async def parsing(make_pipeline, monkeypatch, unparsed_vacancy, session_factory):
    """Конвейер с подставным разбором объявления.

    Разбор проверяется двумя слайсами — приговор и запись, — и обоим нужно
    одно: чтобы обращения к языковой модели отдавали заготовленное, а
    оценка по навыкам не отсекала всё на пороге.
    """
    pipeline = await make_pipeline(known_hr_client())
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик",
        description="Ищем в команду",
        stack_required=["Python"],
        grade="middle",
        salary="200000",
        remote="remote",
        location="Ереван",
    )
    pipeline.parse_refusal = None
    pipeline.parse_asked = False
    # Жанр по умолчанию — вакансия: приговор проверяют слайсы про пригодность
    # и про порог, и заслон жанра не должен отвечать за них.
    pipeline.genre = PostGenre(is_vacancy=True, reason="ищем в команду")
    pipeline.genre_trouble = None
    pipeline.genre_asked = False
    _fit_answers_by_default(pipeline)
    pipeline.asked_to_send = []
    _answer_instead_of_the_model(pipeline, monkeypatch)

    await put(session_factory, profile_row())
    profile = await only_row(session_factory, Profile)
    await put(session_factory, profile_skill_row(profile.id, "Python"))
    await pipeline.reload_resources()
    await pipeline.rs.set_app("scoring_threshold", "1")
    return pipeline, unparsed_vacancy


@pytest.fixture
async def dm_pipeline(monkeypatch, make_pipeline):
    """Конвейер с подставным разбором ответа HR и невзводящимся таймером.

    Накопитель входящих проверяется двумя слайсами — что в нём копится и
    что с ним делает остановка, — и обоим нужно одно: чтобы разбор не
    уходил в языковую модель и не срабатывал сам по себе. Тест, которому
    нужно срабатывание, ставит своё ожидание.
    """
    built = await make_pipeline()
    built.DM_CLASSIFY_DEBOUNCE_SEC = 30
    built.classified = []

    async def classify(pipeline, hr_id):
        built.classified.append((hr_id, built.dm_debounce.take(hr_id)))

    monkeypatch.setattr(dm_classify, "classify_and_apply_for_hr", classify)
    yield built
    await built.cancel_pending_dm_classifications()
