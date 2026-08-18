"""Приём объявления из канала с отсевом перепостов."""

import logging

from sqlalchemy.exc import IntegrityError
import numpy as np

from backend.flows import linked_article, parse
from backend.domain.dedup import cosine_top_match
from backend.message_text import extract_post_text, extract_text
from backend.models import Vacancy
from backend.payloads import ChannelPost
from backend.repository.vacancies_life import add_vacancy_event
from backend.telegram_time import tg_moment

from backend.flows import embeddings

logger = logging.getLogger(__name__)


async def _post_embedding(pipeline, post: ChannelPost):
    """Числовой отпечаток поста; пусто — модель отпечатков не дала.

    Пост без отпечатка пропускается, курсор идёт дальше, и следующий проход по
    каналу его не увидит — но это дешевле, чем встать на одном посте.

    Считается по голому тексту поста, а не по тому, что уходит в разбор и
    ложится в строку: там к посту подставлены адреса ссылок и дописаны статьи,
    а сравнивать отпечаток приходится с посчитанными год назад, когда ни того,
    ни другого в тексте не было. Посчитай его по склейке — и перепост давно
    заведённой вакансии перестал бы с ней сходиться, заведясь второй строкой.
    """
    return await embeddings.embed_text(
        pipeline, extract_text(post.msg), f"[@{post.channel_username}] {post.msg.id}"
    )


async def _resume_or_skip(pipeline, similar_id: int, post: ChannelPost) -> None:
    """Что делать с постом, похожим на уже заведённую вакансию.

    Похожая строка бывает двух родов: настоящий перепост — такой
    пропускается, — и вакансия, брошенная недоразобранной на прошлом
    прогоне. Вторую здесь и дорзабирают: иначе она пропускалась бы вечно.
    """
    if not await parse.is_unparsed_vacancy(pipeline, similar_id):
        logger.info(
            "[@%s] %d duplicate of vacancy %d, skipping",
            post.channel_username, post.msg.id, similar_id,
        )
        return
    logger.info(
        "[@%s] %d matched orphan vacancy %d, finishing parse",
        post.channel_username, post.msg.id, similar_id,
    )
    # Брошенная строка могла прийти из другого канала (перепост): разбираем
    # по тексту нынешнего поста и его каналу, а кладём в ту строку.
    # Совпадение отпечатков ручается, что тексты почти дословны.
    await parse.parse_and_update_vacancy(
        pipeline, similar_id, post.text, post.channel_username
    )


async def ingest_post(
    pipeline, channel_id: int, channel_username: str, msg
) -> None:
    # Cursor advance'ится в `poll_channel` (батчами), не здесь.
    text = extract_post_text(msg)
    if not text or msg.service is not None or msg.poll is not None:
        return
    text, whole = await linked_article.with_linked_articles(text)
    post = ChannelPost(channel_id, channel_username, msg, text)
    embedding = await _post_embedding(pipeline, post)
    if embedding is None:
        return

    await embeddings.ensure_embedding_cache(pipeline, len(embedding))
    similar_id = cosine_top_match(
        np.asarray(embedding, dtype=np.float32),
        pipeline.embedding_ids,
        pipeline.embedding_matrix,
        threshold=pipeline.rs.dedup_cosine_threshold,
    )
    if similar_id is not None:
        await _resume_or_skip(pipeline, similar_id, post)
        return

    new_vacancy_id = await save_new_vacancy(pipeline, post, embedding)
    if new_vacancy_id is not None:
        # Недобравшее объявление выбрасывать нельзя: в таком посте одна шапка
        # со ссылкой, и без статьи разбору видно пустышку. Выброси её — и
        # вакансия пропадёт навсегда, потому что курсор канала уже уехал и
        # второй раз этот пост не прочтут. Пометка «не подходит» дождётся
        # прогона заново, а тот статью и подберёт.
        await parse.parse_and_update_vacancy(pipeline,
            new_vacancy_id, text, channel_username, allow_delete=whole
        )


def _vacancy_row(post: ChannelPost, embedding: list[float]) -> Vacancy:
    """Строка вакансии из поста канала — ещё не разобранная.

    Ссылка собирается из ника и номера поста: по ней человек открывает
    исходное объявление прямо из карточки.
    """
    return Vacancy(
        source_channel_id=post.channel_id,
        source_msg_id=post.msg.id,
        raw_text=post.text,
        embedding=embedding,
        source_url=f"https://t.me/{post.channel_username}/{post.msg.id}",
        posted_at=tg_moment(post.msg.date),
    )


async def save_new_vacancy(
    pipeline,
    post: ChannelPost,
    embedding: list[float],
) -> int | None:
    async with pipeline.session_factory() as session:
        try:
            new_vacancy = _vacancy_row(post, embedding)
            session.add(new_vacancy)
            await session.flush()
            await add_vacancy_event(
                session,
                new_vacancy.id,
                "ingested",
                {
                    "channel": post.channel_username,
                    "msg_id": post.msg.id,
                },
            )
            await session.commit()
            embeddings.append_embedding(pipeline, new_vacancy.id, embedding)
            logger.info(
                "[@%s] %d -> vacancy %d",
                post.channel_username,
                post.msg.id,
                new_vacancy.id,
            )
            return new_vacancy.id
        except IntegrityError:
            await session.rollback()
            logger.info(
                "[@%s] %d uq_vacancy_source race, skipping",
                post.channel_username,
                post.msg.id,
            )
            return None
