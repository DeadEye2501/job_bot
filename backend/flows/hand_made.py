"""Заявка окна «Добавить вакансию»: довести её до строки дорогой её рода.

Отличие от `pasted`: тот доводит до строки вставленный текст, а здесь заявку
любого рода — текст отдают ему, поля и пост по ссылке заводят сами. Поля с выключенным
переключателем заводит мост без бота, но той же `file_fields`; бот получает
их, только когда заведённое надо отдать откликателю, а отклик идёт через место
прогона.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from backend.agent.kit import AgentKit
from backend.domain.telegram_identity import post_address
from backend.flows import ingest, linked_article, pasted
from backend.flows.hand_outcome import HandResult, tell
from backend.flows.handover import Intake, hand_over
from backend.flows.parse import Judged
from backend.payloads import ChannelPost
from backend.repository.channels import find_channel_by_username
from backend.repository.vacancies_life import vacancy_at_address
from backend.repository.vacancies_new import create_vacancy
from backend.telegram_lookup import read_post

HandTab = Literal["fields", "text", "post", "channel"]
"""Род заявки: вкладка окна, а у ссылки — то, на что она ведёт."""


@dataclass(frozen=True)
class HandRequest:
    """Заявка окна: род, введённое (поля формы словарём, текст или адрес),
    названная дата публикации и отдавать ли откликателю."""

    tab: HandTab
    value: str | dict
    posted_at: datetime | None
    hands_over: bool


async def ingest_by_hand(kit: AgentKit, request: HandRequest) -> None:
    """Довести заявку окна до строки; итог — вестью окну (`tell`)."""
    if request.tab == "text":
        await pasted.ingest_pasted_text(
            kit.pipeline, request.value, request.posted_at, request.hands_over
        )
    elif request.tab == "post":
        await _posted(kit.pipeline, request.value, request.hands_over)
    elif request.tab == "channel":
        tell(kit.pipeline, "channel_link")
    else:
        await _filed(kit.pipeline, request.value, request.hands_over)


async def _posted(pipeline, url: str, hands_over: bool) -> None:
    """Завести пост Telegram по ссылке дорогой поста канала, но заведённым
    человеком: без слияния с похожими и без приговора.

    Однозначный повтор — тот же адрес у заведённой строки — узнаётся первым,
    до Telegram: у поста незаведённого или закрытого канала уникальности в
    базе нет. Читается тем же чтением, что пост канала, — со статьями; не
    скачалась статья — строка не заводится, как у вставленного текста:
    человек может нажать ещё раз. Заведён канал поста — строка связана с ним.
    """
    pipeline.emit_progress("pasted", "Разбор объявления", 0, 0)
    async with pipeline.session_factory() as session:
        existing = await vacancy_at_address(session, url)
    if existing is not None:
        tell(pipeline, "duplicate", existing)
        return
    msg, trouble = await read_post(pipeline.client, post_address(url))
    if trouble is not None:
        tell(pipeline, trouble)
        return
    read = await linked_article.post_full_text(msg)
    if read is None:
        tell(pipeline, "empty_post")
        return
    text, whole = read
    if not whole:
        tell(pipeline, "article")
        return
    nick = getattr(msg.chat, "username", None)
    post = ChannelPost(await _channel_id(pipeline, nick), nick or "", msg, text, url)
    by_hand = Intake(channel=nick, hands_over=hands_over, tells_window=True, by_hand=True)

    async def save(embedding: list[float]) -> int | None:
        vacancy_id = await ingest.save_new_vacancy(pipeline, post, embedding, by_hand)
        if vacancy_id is None:
            # Тот же пост завёл встречный обход его канала, пока шло чтение.
            async with pipeline.session_factory() as session:
                tell(pipeline, "duplicate", await vacancy_at_address(session, url))
        return vacancy_id

    await pasted.file_by_hand(pipeline, text, by_hand, save)


async def _channel_id(pipeline, nick: str | None) -> int | None:
    """Номер заведённого канала поста; пусто — канал не заведён или без ника."""
    if nick is None:
        return None
    async with pipeline.session_factory() as session:
        channel = await find_channel_by_username(session, nick)
    return None if channel is None else channel.id


async def file_fields(session_factory, fields: dict) -> HandResult:
    """Завести набранное в окне: заведено — с номером, повтор по «Ссылке на
    объявление» — с номером существующей. Набранное — уже разбор, модели оно
    не отдаётся."""
    async with session_factory() as session:
        async with session.begin():
            vacancy_id, created = await create_vacancy(session, fields)
    return HandResult("ok" if created else "duplicate", vacancy_id)


async def _filed(pipeline, fields: dict, hands_over: bool) -> None:
    """Завести набранное и отдать откликателю; повтор не отдаётся — окно
    перейдёт на существующую."""
    result = await file_fields(pipeline.session_factory, fields)
    if result.outcome == "ok":
        pipeline.fire_vacancies_changed()
    tell(pipeline, result.outcome, result.vacancy_id)
    if result.outcome == "ok":
        await hand_over(pipeline, [(result.vacancy_id, Judged(True))], applies=hands_over)
