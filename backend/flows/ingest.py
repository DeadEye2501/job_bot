"""Приём объявления из канала с отсевом перепостов."""

import logging

from sqlalchemy.exc import IntegrityError
import numpy as np

from adapters import lm_studio
from backend.flows import parse
from backend.domain.dedup import cosine_top_match
from backend.helpers import extract_text
from backend.models import Vacancy
from backend.models import VacancyEvent

from backend.flows import embeddings

logger = logging.getLogger(__name__)


async def ingest_post(
    pipeline, channel_id: int, channel_username: str, msg
) -> None:
    # Cursor advance'ится в `poll_channel` (батчами), не здесь.
    text = extract_text(msg)
    if not text or msg.service is not None or msg.poll is not None:
        return

    try:
        embedding = await lm_studio.embed(
            pipeline._lm_embed_client, pipeline._lm_embed_model, text
        )
    except RuntimeError as e:
        logger.warning(
            "[@%s] %d embed shape error: %s, skipping",
            channel_username,
            msg.id,
            e,
        )
        return

    await embeddings.ensure_embedding_cache(pipeline)
    similar_id = cosine_top_match(
        np.asarray(embedding, dtype=np.float32),
        pipeline._embedding_ids,
        pipeline._embedding_matrix,
        threshold=pipeline._rs.dedup_cosine_threshold,
    )
    if similar_id is not None:
        # Could be a real duplicate, or the embedding of a vacancy left
        # half-built by a cancelled previous cycle (saved with raw_text
        # + embedding but no parsed fields). Detect the orphan and
        # finish parsing it now instead of skipping forever.
        unparsed = await parse.is_unparsed_vacancy(pipeline, similar_id)
        if unparsed:
            logger.info(
                "[@%s] %d matched orphan vacancy %d, finishing parse",
                channel_username, msg.id, similar_id,
            )
            # Note: if the orphan was originally ingested from a different
            # channel (cross-channel re-post), we parse using THIS post's
            # text + channel hint and stamp it onto the original row. The
            # embedding match guarantees texts are near-identical, so this
            # is acceptable.
            await parse.parse_and_update_vacancy(pipeline, 
                similar_id, text, channel_username
            )
        else:
            logger.info(
                "[@%s] %d duplicate of vacancy %d, skipping",
                channel_username, msg.id, similar_id,
            )
        return

    new_vacancy_id = await save_new_vacancy(pipeline, 
        channel_id, channel_username, msg, text, embedding
    )
    if new_vacancy_id is not None:
        await parse.parse_and_update_vacancy(pipeline, 
            new_vacancy_id, text, channel_username
        )


async def save_new_vacancy(
    pipeline,
    channel_id: int,
    channel_username: str,
    msg,
    text: str,
    embedding: list[float],
) -> int | None:
    async with pipeline._session_factory() as session:
        try:
            new_vacancy = Vacancy(
                source_channel_id=channel_id,
                source_msg_id=msg.id,
                raw_text=text,
                embedding=embedding,
                source_url=f"https://t.me/{channel_username}/{msg.id}",
                posted_at=msg.date,
            )
            session.add(new_vacancy)
            await session.flush()
            session.add(
                VacancyEvent(
                    vacancy_id=new_vacancy.id,
                    kind="ingested",
                    payload={
                        "channel": channel_username,
                        "msg_id": msg.id,
                    },
                )
            )
            await session.commit()
            embeddings.append_embedding(pipeline, new_vacancy.id, embedding)
            logger.info(
                "[@%s] %d -> vacancy %d",
                channel_username,
                msg.id,
                new_vacancy.id,
            )
            return new_vacancy.id
        except IntegrityError:
            await session.rollback()
            logger.info(
                "[@%s] %d uq_vacancy_source race, skipping",
                channel_username,
                msg.id,
            )
            return None
