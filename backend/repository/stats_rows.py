"""Строка таблицы источников на экране статистики: кто прислал, сколько, куда дошло."""

SourceKey = tuple[int | None, int | None]
"""Источник строки — пара «канал, агрегатор»; обе пусты у заведённого руками."""


def source_item(
    key: SourceKey,
    title: str | None,
    username: str | None,
    counts: tuple[int, int, int] = (0, 0, 0),
) -> dict:
    """Строка источника в таблице статистики.

    Строку собирают два прохода — по тем, кто прислал что-то в окне, и по
    тем, кто попал в неё только воронкой. Разойдись сборка, один и тот же
    источник выглядел бы в таблице по-разному в зависимости от того, каким
    проходом он туда попал.

    Счётчики приходят тройкой, потому что тройкой их и отдаёт запрос; у
    источника, попавшего в таблицу воронкой, их нет вовсе, и нули у него
    значат «ничего не было», а не «пока неизвестно».

    Подписи здесь нет: её собирает окно. У канала это название и ник, у
    агрегатора — его имя в `title`; строка без обоих — всё заведённое руками.
    """
    channel_id, aggregator_id = key
    total_vac, rerun_trash, not_fit = counts
    return {
        "id": channel_id,
        "aggregator_id": aggregator_id,
        "kind": "channel" if channel_id else "aggregator" if aggregator_id else "none",
        "title": title,
        "username": username,
        "_total_vac": int(total_vac or 0),
        "_rerun_trash": int(rerun_trash or 0),
        "not_fit": int(not_fit or 0),
    }


def pipeline_row(key: SourceKey, item: dict, trash_events: int, funnel) -> dict:
    """Строка таблицы по одному источнику: ингест, воронка и две доли.

    Всего — это и строки вакансий, и удалённый мусор: последнего в
    `vacancy` уже нет, а прислан источником он был.

    Доли считаются по одной когорте: и в числителе, и в знаменателе только
    те вакансии, отклик на которые ушёл внутри окна. Считай мы числитель по
    своему множеству — вакансия, откликнутая до окна и ответившая внутри,
    попадала бы в числитель, минуя знаменатель, и доля переваливала бы за
    сотню. Столбцы воронки рядом остаются как есть: они отвечают на другой
    вопрос — сколько вообще прошло ступень за период.

    При нуле отправленных долей нет вовсе — ноль там означал бы «отвечают
    нулю процентов», а не «спрашивать не с чего».
    """
    total = item["_total_vac"] + trash_events
    trash = trash_events + item["_rerun_trash"]
    not_fit = item["not_fit"]
    reached = {name: by_source.get(key, set()) for name, by_source in funnel.items()}
    counts = {name: len(ids) for name, ids in reached.items()}
    sent_ids = reached["sent"]

    def share(stage: str) -> float | None:
        if not sent_ids:
            return None
        return round(len(reached[stage] & sent_ids) / len(sent_ids) * 100, 1)

    return {
        "id": item["id"],
        "aggregator_id": item["aggregator_id"],
        "kind": item["kind"],
        "title": item["title"],
        "username": item["username"],
        "total": total,
        "trash": trash,
        "not_fit": not_fit,
        "fit": max(0, total - trash - not_fit),
        **counts,
        "conv_answ_sent": share("answered"),
        "conv_invite_sent": share("invite_plus"),
    }
