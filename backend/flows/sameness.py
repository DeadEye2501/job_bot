"""Узнать в тексте заведённую вакансию: новая, повтор разобранной или брошенная недоразобранной."""

from dataclasses import dataclass

from backend.flows import embeddings, parse


@dataclass(frozen=True)
class Match:
    """Чем оказался текст: новым (`new`), повтором разобранной (`parsed`) или
    брошенной недоразобранной (`unparsed`) вакансии; вектор — для новой строки."""

    kind: str
    vacancy_id: int | None
    embedding: list[float] | None


async def known_or_new(pipeline, text: str, what: str) -> Match | None:
    """Вектор текста и похожая заведённая вакансия. Пусто — модель не ответила.

    Недоразобранная похожая — не повтор, а брошенная строка: её дочитывают
    новым текстом. Молчание поставщика (`ProviderIsSilent`) пробрасывается:
    зовущему решать, отказ это или пропуск.
    """
    embedding = await embeddings.embed_text(pipeline, text, what)
    if embedding is None:
        return None
    similar = await embeddings.similar_vacancy_id(pipeline, embedding)
    if similar is None:
        return Match("new", None, embedding)
    unparsed = await parse.is_parsed(pipeline.session_factory, similar) is False
    return Match("unparsed" if unparsed else "parsed", similar, embedding)
