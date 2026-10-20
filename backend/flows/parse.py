"""Приговор объявлению: разбор моделью, вердикт по разобранному и что дальше.

Всё здесь про одно — чем объявление кончилось: спросить модель, свериться с
чёрным списком, вынести приговор, выбросить мусор, пометить пустышку. Куда
исход ложится, знает сосед (`flows/parse_write`); зовут его отсюда, а не
наоборот. Откликаться ли, решает не разбор, а передача (`flows/handover`).
"""

import logging
from dataclasses import dataclass

from backend.flows.fit_refusal import unanswered, unfit_refusal
from backend.domain.blacklist import check_blacklist
from backend.domain.contact_keys import is_link
from backend.domain.resume_marks import resume_mark
from backend.domain.scoring import score_stack
from backend.domain.verdict import blacklist_refusal, decide_vacancy_status
from backend.domain.verdict import is_empty_vacancy
from backend.domain.verdict import EMPTY_SKIP_REASON, TRASH_SKIP_PREFIX
from backend.llm.rules import VACANCY_TEXT_CHARS
from backend.llm.vacancy import parse_vacancy
from backend.models import HR, Vacancy
from backend.payloads import ParsedVacancy
from backend.models import VacancyStatus

from backend.flows import cleanup
from backend.flows.parse_write import Outcome, persist_parse_outcome
from backend.repository.aggregators import barred_host_of
from backend.repository.vacancies_new import made_by_hand
from backend.repository.vacancy_contacts import vacancy_addresses

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Judged:
    """Итог разбора: записан ли исход и HR, заведённый этим разбором."""

    stored: bool
    fresh_hr: HR | None = None


def _judged(written) -> "Judged":
    """Итог по ответу записи: не дошла — не записан; новый HR — отдаётся."""
    if written is None:
        return Judged(False)
    hr, created = written
    return Judged(True, hr if created else None)


async def _dropped_as_trash(
    pipeline, vacancy_id: int, reason: str, *, allow_delete: bool
) -> bool:
    """Убрать непригодную вакансию, если убирать разрешено; сказать, убрали ли.

    Приговор «непригодна» выносят трое — пустышке, метке соискательского
    поста и вердикту модели, — а развилка у них одна. Разрешение приходит
    доводом от зовущего и говорит об одном: ручается ли тот за текст, по
    которому вынесен приговор. Приём поста ручается, приговора без полного
    текста он и не выносит; подбор недоразобранного ручается за текст, полнее
    которого уже не станет. Прогон заново не разрешает никогда: строку человек
    открыл руками, и исчезнуть у него из-под курсора она не должна —
    непригодность остаётся пометкой в причине отказа.
    """
    if not allow_delete:
        logger.info(
            "vacancy %s: %s, marking Not Fit (deleting not allowed here)",
            vacancy_id, reason,
        )
        return False
    logger.info("vacancy %s: %s, deleting as trash", vacancy_id, reason)
    await cleanup.delete_vacancy_as_trash(pipeline, vacancy_id, reason=reason)
    return True


async def _thrown_out_as_a_resume(
    pipeline, vacancy_id: int, mark: str, allow_delete: bool
) -> Judged:
    """Убрать пост соискателя, не спрашивая модель вовсе; сказать, вышло ли.

    Поля у такой строки не заполняются: разбора не было, а показывать в
    карточке разобранное прошлым заходом рядом с приговором «мусор» — значит
    выдавать старое за новое.
    """
    reason = f"{TRASH_SKIP_PREFIX}пост соискателя, метка {mark}"
    logger.info("vacancy %s: пост соискателя, метка %s", vacancy_id, mark)
    if await _dropped_as_trash(
        pipeline, vacancy_id, reason, allow_delete=allow_delete
    ):
        return Judged(True)
    return await save_empty_vacancy(pipeline, vacancy_id, None, reason=reason)


async def _parsed_or_dropped(
    pipeline, vacancy_id: int, text: str, channel_username: str, allow_delete: bool
):
    """Разобрать объявление; пустота в ответ — с ним уже покончено.

    Три значения: разбор, отказ модели и итог записи. Третий нужен только
    пустой дороге: там строку записывают, и сорвавшаяся запись не должна
    доехать до окна словом «разобрана».

    Пустышку отсеиваем до модели-оценщика: разбор не вытащил ни одного поля
    сверх названия, и второе обращение к модели ей не положено. Дорога эта не
    только для мемов, обрывков и рекламных строчек — сюда же наставление
    разбора сводит пост соискателя, веля отдать по нему пустоту вместо полей.
    Приговор «пусто» поэтому значит «вакансии тут нет», а не «мы не
    справились». Дальше две дороги — удалить или пометить, — и выбор между
    ними держит `_dropped_as_trash`.

    Не состоявшееся обращение к модели на эти дороги не выходит вовсе и
    отдаётся отдельно: приговора не было, значит и выбрасывать нечего.
    Строка остаётся неразобранной, за ней вернётся подбор недоразобранного.
    Удали её здесь — и пост не вернётся ничем: курсор канала уже сдвинут.
    """
    parsed, refusal, trouble = await _asked_model(pipeline, vacancy_id, text, channel_username)
    if trouble is not None:
        reason, unasked = trouble
        if unasked:
            return None, refusal, Judged(False)
        return None, None, await save_empty_vacancy(
            pipeline, vacancy_id, None, reason=reason
        )
    if not is_empty_vacancy(parsed):
        return parsed, None, Judged(True)
    if await _dropped_as_trash(
        pipeline, vacancy_id, EMPTY_SKIP_REASON, allow_delete=allow_delete
    ):
        return None, None, Judged(True)
    return None, None, await save_empty_vacancy(pipeline, vacancy_id, parsed)


async def _asked_model(pipeline, vacancy_id: int, text: str, channel_username: str | None):
    """Разбор объявления моделью: поля, отказ модели и что с этим отказом делать
    (`unanswered`: пусто — отказа не было)."""
    parsed, refusal = await parse_vacancy(
        text,
        pipeline.lm_client,
        pipeline.lm_chat_model,
        channel_username=channel_username,
        profile=pipeline.profile_cache,
    )
    return parsed, refusal, unanswered("разбор", refusal, vacancy_id)


def _score(pipeline, parsed) -> int:
    """Балл разобранного по анкете: обязательный стек весит больше желательного."""
    return score_stack(parsed.stack_required, parsed.stack_preferred, pipeline.skills_cache)


async def _parsed_by_hand(
    pipeline, vacancy_id: int, text: str, channel_username: str | None
) -> Judged:
    """Разобрать заведённую человеком: поля заполняются, приговора нет вовсе.

    Человек её добавил — значит, хочет откликнуться. Ни метки поста
    соискателя, ни чёрного списка, ни «вакансия ли это» и пригодности, ни
    порога балла: не вынести и переписать, а не звать. Исход — New, и снести
    её как мусор нельзя.

    Обрыв и отказ модели тоже кончаются New: строка встаёт в список без
    разобранных полей, и человек видит её там, куда сам её положил. Молчание
    провайдера приговором не является и здесь — строка ждёт следующего захода.
    """
    parsed, _refusal, trouble = await _asked_model(pipeline, vacancy_id, text, channel_username)
    if trouble is not None:
        _reason, unasked = trouble
        if unasked:
            return Judged(False)
        parsed = None
    score = 0 if parsed is None else _score(pipeline, parsed)
    outcome = Outcome(
        status=VacancyStatus.NEW, skip_reason=None, score=score,
        keep_previous_stack=parsed is not None,
    )
    return await _finish_parse(pipeline, vacancy_id, parsed, outcome)


async def _barred_site(pipeline, vacancy_id: int, found: list[str]) -> str | None:
    """Сайт из отсева, на который ведёт вакансия: адрес её страницы или ссылка в контактах.

    `found` — контакты идущего разбора: в базу они ложатся после приговора, а
    сверить надо и их. Почта не сверяется: у неё решало бы написание — ящик на
    поддомене сайта отсеивался бы, а на самом сайте нет.
    """
    async with pipeline.session_factory() as session:
        addresses = [*await vacancy_addresses(session, vacancy_id), *found]
        return await barred_host_of(session, [link for link in addresses if is_link(link)])


async def _verdict_for(
    pipeline, parsed, text: str, vacancy_id: int
) -> tuple | None:
    """Приговор объявлению: статус, причина отказа и баллы; пусто — не спросили.

    **Порог стоит за вопросом «вакансия ли это», а не перед ним.** Баллы
    отвечают, подходит ли вакансия кандидату, и к посту, вакансией не
    являющемуся, неприменимы: чужое резюме они отсеивают случайно, навыками
    мимо анкеты. На случайность начинают рассчитывать — отсев выглядит
    работающим фильтром ровно до того резюме, которое баллы наберёт, а по
    нему уходит письмо живому человеку.

    Чёрный список, наоборот, впереди: он не догадка о посте, а решение
    человека, и жанр поста его не меняет. Читает он весь исходный текст, а
    модели достаётся урезанный по её бюджету. Сайты из отсева сверяются не с
    текстом, а с адресом вакансии и её контактами: отметка сайта отсеивает то,
    что на нём живёт, а не всякий пост, где он назван.
    """
    score = _score(pipeline, parsed)
    barred = await _barred_site(pipeline, vacancy_id, parsed.other_contacts)
    blocked = blacklist_refusal(check_blacklist(text, pipeline.blacklist_patterns) or barred)
    logger.debug(
        "vacancy %s: score=%d threshold=%d blacklist=%s",
        vacancy_id, score, pipeline.rs.scoring_threshold, blocked,
    )
    if blocked is not None:
        return VacancyStatus.NOT_FIT, blocked, score
    refusal, unasked = await unfit_refusal(pipeline, parsed, text, vacancy_id)
    if unasked:
        return None
    if refusal is not None:
        return VacancyStatus.NOT_FIT, refusal, score
    status, skip_reason = decide_vacancy_status(
        score, threshold=pipeline.rs.scoring_threshold
    )
    return status, skip_reason, score


async def _finish_parse(pipeline, vacancy_id: int, parsed, outcome: Outcome) -> Judged:
    """Записать исход. Не дошла запись — человеку говорят «не удалось», а не
    «готово» над карточкой, которая не менялась."""
    return _judged(await persist_parse_outcome(pipeline, vacancy_id, parsed, outcome))


async def _thrown_out_by_the_verdict(
    pipeline, vacancy_id: int, skip_reason: str | None, allow_delete: bool
) -> bool:
    """Убрать строку, если так решил приговор; сказать, убрали ли.

    Метку мусора ставит один — заслон жанра, — и значит она одно: это не
    вакансия. Зовы о пригодности такой метки не выносят: они отвечают о
    пригодности вакансии, признанной вакансией до них. Метка соискательского
    поста сюда не приходит тоже, она решает раньше и своей дорогой
    (`_thrown_out_as_a_resume`).
    """
    return bool(
        skip_reason
        and skip_reason.startswith(TRASH_SKIP_PREFIX)
        and await _dropped_as_trash(
            pipeline, vacancy_id, skip_reason, allow_delete=allow_delete
        )
    )


async def parse_and_update_vacancy(
    pipeline, vacancy_id: int, text: str, channel_username: str | None,
    *, allow_delete: bool = True,
) -> Judged:
    """Разобрать объявление, вынести приговор и записать исход; сказать, вышло ли.

    ``allow_delete`` разводит две дороги: непригодную строку удаляют там, где
    зовущий ручается за текст приговора; прогон заново не разрешает никогда.

    «Не вышло» — спросить модель не удалось либо исход не записался; пустой
    разбор к ним не относится, это состоявшийся приговор. Различие нужно окну.

    Метка соискательского поста стоит раньше разбора: она стоит ноль.

    Заведённая человеком судится одним решением здесь, в начале, а не
    приговором, переписанным после: приговора у неё нет (`_parsed_by_hand`).
    """
    async with pipeline.session_factory() as session:
        by_hand = await made_by_hand(session, vacancy_id)
    if by_hand:
        return await _parsed_by_hand(pipeline, vacancy_id, text, channel_username)
    mark = resume_mark(text[:VACANCY_TEXT_CHARS])
    if mark is not None:
        return await _thrown_out_as_a_resume(pipeline, vacancy_id, mark, allow_delete)
    parsed, refusal, stored = await _parsed_or_dropped(
        pipeline, vacancy_id, text, channel_username, allow_delete
    )
    if refusal is not None:
        return Judged(False)
    if parsed is None:
        return stored
    verdict = await _verdict_for(pipeline, parsed, text, vacancy_id)
    if verdict is None:
        return Judged(False)
    status, skip_reason, score = verdict
    if await _thrown_out_by_the_verdict(
        pipeline, vacancy_id, skip_reason, allow_delete
    ):
        return Judged(True)
    return await _finish_parse(
        pipeline,
        vacancy_id,
        parsed,
        Outcome(
            status=status,
            skip_reason=skip_reason,
            score=score,
            keep_previous_stack=True,
        ),
    )


async def is_parsed(session_factory, vacancy_id: int) -> bool | None:
    """Разобрана ли строка; пусто — строки нет.

    Недоразобранная — брошенная: строка и вектор есть, а разбор не кончился
    (процесс упал, модель промолчала). Читается явное поле, а не отсутствие
    названия: у отбракованного пустого объявления названия нет, а разобрано оно
    до конца.
    """
    async with session_factory() as session:
        v = await session.get(Vacancy, vacancy_id)
    return None if v is None else v.is_parsed


async def save_empty_vacancy(
    pipeline, vacancy_id: int, parsed: ParsedVacancy | None,
    *, reason: str = EMPTY_SKIP_REASON,
) -> Judged:
    """Записать непригодную строку пометкой, когда удалять её нельзя.

    Пишется то, что разбор всё же вытащил, — обычно заголовок и ещё один
    сигнал из пяти, по которым выносится приговор «пусто»: человек видит
    вакансию в окне и решает руками. Что именно записалось, считается по
    строке после записи (`_fields_filled`), а не предполагается заранее.

    Пустой разбор чистит поля. Приходит он двумя дорогами: разбора не было
    вовсе — пост опознан по метке — либо он не дал даже названия. Оставь мы
    прежние поля, окно показало бы разобранное прошлым заходом рядом с
    приговором «мусор», то есть выдало бы старое за новое.
    """
    return await _finish_parse(pipeline, vacancy_id, parsed, Outcome(
        status=VacancyStatus.NOT_FIT,
        skip_reason=reason,
        score=0,
        keep_previous_stack=False,
    ))
