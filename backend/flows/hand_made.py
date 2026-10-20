"""Заявка окна «Добавить вакансию»: довести её до строки дорогой её рода.

Отличие от `pasted`: тот доводит до строки вставленный текст, а здесь заявку
любого рода — текст и статью отдают ему, страницу — агенту (`linked_page`),
поля и пост по ссылке заводят сами. Поля с выключенным
переключателем заводит мост без бота, но той же `file_fields`; бот получает
их, только когда заведённое надо отдать откликателю, а отклик идёт через место
прогона.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from backend.agent.kit import AgentKit
from backend.domain.hosts import LinkKind, article_address, typed_page
from backend.domain.telegram_identity import post_address
from backend.flows import handover, ingest, linked_article, linked_page, pasted
from backend.flows.hand_outcome import HandResult, show_parsing, tell
from backend.flows.handover import hand_over
from backend.flows.parse import Judged
from backend.payloads import ChannelPost
from backend.repository.channels import find_channel_by_username
from backend.repository.vacancies_life import vacancy_at_address
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

    Однозначный повтор узнаётся первым (`_known_address`): ни Telegram, ни
    агент, ни модель ради уже заведённой вакансии не зовутся. Статья по ссылке
    — тот же вставленный текст из одной ссылки, без проверки повтора: адрес
    статьи — не страница вакансии.
    """
    pipeline = kit.pipeline
    if await _known_address(pipeline, _own_address(request)):
        return
    if request.tab == "text":
        await pasted.ingest_pasted_text(pipeline, request.value, request.posted_at, request.hands_over)
    elif request.tab == "article":
        await pasted.ingest_pasted_text(pipeline, article_address(request.value), None, request.hands_over)
    elif request.tab == "post":
        await _posted(pipeline, request.value, request.hands_over)
    elif request.tab == "page":
        await linked_page.ingest_page(kit, request.value, handover.hand_made_intake(request.hands_over))
    elif request.tab in _NOTHING_TO_READ:
        tell(pipeline, _NOTHING_TO_READ[request.tab])
    else:
        await _filed(pipeline, request.value, request.hands_over)


def _own_address(request: HandRequest) -> str | None:
    """Собственный адрес вакансии в заявке: у поста и страницы — сама ссылка,
    у полей — «Ссылка на объявление»; у текста и статьи его нет."""
    if request.tab in ("post", "page"):
        return request.value
    if request.tab == "fields":
        return typed_page(request.value.get("source_url"))
    return None


async def _known_address(pipeline, url: str | None) -> bool:
    """Заведена ли уже вакансия с этим адресом; да — окну сказано (`known_and_told`)."""
    if not url:
        return False
    async with pipeline.session_factory() as session:
        existing = await vacancy_at_address(session, url)
    return existing is not None and await handover.known_and_told(pipeline, existing)


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
