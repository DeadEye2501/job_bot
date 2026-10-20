"""Заявка окна «Добавить вакансию»: довести её до строки дорогой её рода.

Отличие от `pasted`: тот доводит до строки вставленный текст, а здесь заявку
любого рода — текст и статью отдают ему, страницу — агенту (`linked_page`),
поля и пост по ссылке заводят сами. Поля с выключенным
переключателем заводит мост без бота, но той же `file_fields`; бот получает
их, только когда заведённое надо отдать откликателю, а отклик идёт через место
прогона.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Literal

from backend.agent.kit import AgentKit
from backend.domain.hosts import LinkKind, article_address, typed_page
from backend.domain.telegram_identity import post_address
from backend.flows import cleanup, hand_repeat, handover, ingest, linked_article, linked_page, pasted
from backend.flows.hand_outcome import show_parsing, tell
from backend.flows.handover import hand_over
from backend.flows.parse import Judged
from backend.payloads import ChannelPost
from backend.repository.channels import find_channel_by_username
from backend.repository.vacancies_new import create_vacancy
from backend.telegram_lookup import read_post

HandTab = Literal["fields", "text", "link", LinkKind]
"""Род заявки: вкладка окна, а у ссылки — то, на что она ведёт (`link_kind`).

«Ссылка» — род, с которым заявка приходит из окна; ниже бота она идёт уже
родом самого адреса.
"""

_NOTHING_TO_READ = {"channel": "channel_link", "telegram": "no_vacancy"}
"""Ссылки, по которым нечего читать: на канал вместо поста и прочий Telegram,
куда агенту хода нет."""


@dataclass(frozen=True)
class HandRequest:
    """Заявка окна: род, введённое (поля формы словарём, текст или адрес),
    названная дата публикации и отдавать ли откликателю."""

    tab: HandTab
    value: str | dict
    posted_at: datetime | None
    hands_over: bool


async def ingest_by_hand(kit: AgentKit, request: HandRequest) -> None:
    """Довести заявку окна до строки; итог — вестью окну (`tell`).

    Однозначный повтор по собственному адресу узнаётся первым
    (`hand_repeat`): ни Telegram, ни агент, ни модель ради уже заведённой
    вакансии не зовутся. У полей его узнаёт их же заведение (`file_fields`).
    Статья по ссылке — тот же вставленный текст из одной ссылки, без проверки
    повтора: адрес статьи — не страница вакансии.
    """
    pipeline = kit.pipeline
    if request.tab == "fields":
        await _filed(pipeline, request.value, request.hands_over)
        return
    if await hand_repeat.known_and_told(pipeline, await hand_repeat.addressed(pipeline.session_factory, _own_address(request))):
        return
    if request.tab == "text":
        await pasted.ingest_pasted_text(pipeline, request.value, request.posted_at, request.hands_over)
    elif request.tab == "article":
        await pasted.ingest_pasted_text(pipeline, article_address(request.value), None, request.hands_over)
    elif request.tab == "post":
        await _posted(pipeline, request.value, request.hands_over)
    elif request.tab == "page":
        await linked_page.ingest_page(kit, request.value, handover.hand_made_intake(request.hands_over))
    else:
        tell(pipeline, _NOTHING_TO_READ[request.tab])


def _own_address(request: HandRequest) -> str | None:
    """Собственный адрес вакансии в ссылке: у поста и страницы — сама ссылка;
    у прочих родов его нет."""
    return request.value if request.tab in ("post", "page") else None


async def _posted(pipeline, url: str, hands_over: bool) -> None:
    """Завести пост Telegram по ссылке дорогой поста канала, но заведённым
    человеком: без слияния с похожими и без приговора.

    Читается тем же чтением, что пост канала, — со статьями; не скачалась
    статья — строка не заводится, как у вставленного текста: человек может
    нажать ещё раз. Заведён канал поста — строка связана с ним.
    """
    show_parsing(pipeline)
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
    by_hand = handover.hand_made_intake(hands_over, nick)

    async def save(embedding: list[float]) -> int | None:
        vacancy_id = await ingest.save_new_vacancy(pipeline, post, embedding, by_hand)
        if vacancy_id is None:
            # Тот же пост завёл встречный обход его канала, пока шло чтение;
            # либо канала не стало, и тогда строки по адресу нет вовсе.
            found = await hand_repeat.addressed(pipeline.session_factory, url)
            tell(pipeline, "duplicate", found[0] if found else None)
        return vacancy_id

    await pasted.file_by_hand(pipeline, text, by_hand, save)


async def _channel_id(pipeline, nick: str | None) -> int | None:
    """Номер заведённого канала поста; пусто — канал не заведён или без ника."""
    if nick is None:
        return None
    async with pipeline.session_factory() as session:
        channel = await find_channel_by_username(session, nick)
    return None if channel is None else channel.id


async def file_fields(
    session_factory, fields: dict, forget: Callable[[int], Awaitable[object]]
) -> tuple[int, bool]:
    """Завести набранное в окне: номер строки и заведена ли она сейчас.

    Набранное — уже разбор, модели оно не отдаётся. Повтор по «Ссылке на
    объявление» (`hand_repeat.known_among`) отвечает номером существующей.
    Одно заведение у бота и у «Полей» мимо бота — разные у них только руки
    сноса недоразобранной.
    """
    known = await hand_repeat.known_among(
        session_factory, await hand_repeat.addressed(session_factory, typed_page(fields.get("source_url"))), forget)
    if known is not None:
        return known, False
    async with session_factory() as session:
        async with session.begin():
            return await create_vacancy(session, fields), True


async def _filed(pipeline, fields: dict, hands_over: bool) -> None:
    """Завести набранное и отдать откликателю."""
    vacancy_id, created = await file_fields(
        pipeline.session_factory, fields, partial(cleanup.forget_vacancy, pipeline))
    if not created:
        tell(pipeline, "duplicate", vacancy_id)
        return
    pipeline.fire_vacancies_changed()
    tell(pipeline, "ok", vacancy_id)
    await hand_over(pipeline, [(vacancy_id, Judged(True))], applies=hands_over)
