"""Какой приговор получает объявление после разбора.

Порядок отсева выстроен от общего вопроса к частному: сперва «вакансия ли
это», потом «подходит ли она кандидату». Пустышка — мем, обрывок, рекламная
строчка — отсеивается прямо на разборе, обращением к модели за неё платить
незачем; следом метка соискательского поста, она стоит ноль. Дальше идёт
проверяльщик, и только признанное вакансией судят чёрный список и порог по
навыкам: к посту, который вакансией не является, они неприменимы вовсе.

Проверяльщик, не давший ответа, приравнивается к отказу. Сомнение здесь решается
в пользу бездействия: откликнуться на вакансию, о которой ничего не известно,
хуже, чем не откликнуться.

Удаление разрешено только при обычном сборе. При повторном прогоне тот же
приговор оставляет карточку с пометкой: пользователь просил перечитать
вакансию, а не выбросить её.
"""

from backend.domain.verdict import TRUNCATED_SKIP_REASON
from backend.flows import parse
from backend.llm.answers import TRUNCATED_TROUBLE
from backend.llm.rules import VACANCY_TEXT_CHARS
from backend.models import TrashEvent, Vacancy, VacancyStatus
from backend.payloads import FitValidation, PostGenre
from tests.dbio import all_rows, only_row


async def test_a_fitting_vacancy_stays_new(parsing, session_factory):
    """Прошедшая всё вакансия остаётся новой и ждёт отклика."""
    pipeline, vacancy = parsing

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs")

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NEW
    assert saved.skip_reason is None


async def test_an_empty_post_is_thrown_out_on_ingest(parsing, session_factory):
    """Пустышка при обычном сборе выбрасывается, оставив отметку.

    Мемы и обрывки приходят потоком; держать их в списке вакансий
    значило бы утопить в них настоящие.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = None

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs", allow_delete=True)

    assert await all_rows(session_factory, Vacancy) == []
    mark = await only_row(session_factory, TrashEvent)
    assert mark.reason == "empty: no meaningful fields"


async def test_a_resume_mark_decides_before_the_fit_check(parsing, session_factory):
    """Метка резюме выбрасывает пост сама, не спрашивая оценщика.

    Цена промаха тут не строка в списке, а письмо живому человеку от нашего
    имени: отклик с приложенным CV уходит соискателю. Оценщик такие посты
    пропускает — на настроение модели тут полагаться нечем, а метка
    однозначна и стоит ноль.
    """
    pipeline, vacancy = parsing

    await parse.parse_and_update_vacancy(
        pipeline,
        vacancy.id,
        "#cv #python #django\n\nПозиция: Python Developer\nКонтакты: @nnekojiru",
        "jobs",
        allow_delete=True,
    )

    assert await all_rows(session_factory, Vacancy) == []
    assert pipeline.parse_asked is False
    assert pipeline.genre_asked is False
    assert pipeline.validated is False
    mark = await only_row(session_factory, TrashEvent)
    assert mark.reason == "trash: пост соискателя, метка #cv"


async def test_a_mark_beyond_the_models_horizon_does_not_delete(parsing, session_factory):
    """Метка за пределом того, что видит модель, строку не сносит.

    Отсечка судит одна и удаляет без возврата, а модели достаётся урезанный
    по её бюджету текст. Суди отсечка по большему — она сносила бы вакансию
    по метке, которой ни один зов к модели даже не увидел; к тексту при этом
    дописаны статьи по ссылкам, и хэштег в чужой статье не редкость.
    """
    pipeline, vacancy = parsing
    far_away = "Ищем Python-разработчика. " + "а" * VACANCY_TEXT_CHARS + " #cv"

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, far_away, "jobs", allow_delete=True
    )

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NEW


async def test_a_hashtag_inside_a_link_is_not_a_mark(parsing, session_factory):
    """Якорь внутри адреса меткой не считается.

    В `https://acme.com/careers#resume` решётка стоит посреди слова. С пункта
    1 к тексту объявления дописываются ещё и статьи по ссылкам, где таких
    адресов вдоволь, а удаление вакансии необратимо.
    """
    pipeline, vacancy = parsing

    await parse.parse_and_update_vacancy(
        pipeline,
        vacancy.id,
        "Ищем Python-разработчика. Откликнуться: https://acme.com/careers#resume",
        "jobs",
        allow_delete=True,
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NEW


async def test_a_hiring_post_that_says_it_is_looking_survives(parsing, session_factory):
    """Пост о найме с «#ищу» проходит отсев по меткам насквозь.

    Метка `#ищу` в канале означает и «ищу работу», и «ищу сотрудника»: она
    стоит и в постах о найме, где рядом `#вакансия`, `#hiring` и
    `#требуется`. В набор решающих она поэтому не входит — реши она сама,
    настоящие вакансии уходили бы в мусор без возврата. Наблюдается это тем,
    что пост доживает до оценщика, а не приговаривается раньше.
    """
    pipeline, vacancy = parsing

    await parse.parse_and_update_vacancy(
        pipeline,
        vacancy.id,
        "#vacancy #вакансия #job #работа #hiring #требуется #ищу\n\nProduct Manager",
        "jobs",
        allow_delete=True,
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NEW
    assert pipeline.validated is True


async def test_a_vacancy_survives_a_provider_that_did_not_answer(
    parsing, session_factory
):
    """Не ответивший провайдер объявление не выбрасывает.

    Отказ модели и приговор «это не вакансия» — разные вещи, и удалять
    строку имеет право только второй. Наблюдается это тем, что чужой
    приговор из обстановки остался нетронутым: своего разбор не выносил,
    а значит строку подберёт следующий заход.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = None
    pipeline.parse_refusal = "empty_content"

    done = await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=True
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.id == vacancy.id
    assert saved.is_parsed is False
    # Чужой приговор из обстановки — на месте: своего разбор не выносил.
    assert saved.skip_reason == "прошлый отказ"
    assert await all_rows(session_factory, TrashEvent) == []
    assert done is False


async def test_an_empty_post_is_only_marked_on_a_rerun(parsing, session_factory):
    """Пустышка при повторном прогоне остаётся карточкой с пометкой.

    Кнопку нажал пользователь; молча удалить вакансию у него из-под рук
    — не то, о чём он просил.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = None

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs", allow_delete=False)

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "empty: no meaningful fields"


async def test_an_empty_post_never_reaches_the_validator(parsing):
    """Пустышка до проверки пригодности не доходит.

    Она отсеивается раньше нарочно: платить обращением к модели за мем
    незачем.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = None

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs", allow_delete=False)

    assert pipeline.validated is False


async def test_a_blacklisted_post_is_marked_unfit(parsing, session_factory):
    """Объявление, попавшее под чёрный список, помечается непригодным."""
    pipeline, vacancy = parsing
    pipeline.blacklist_patterns = ["казино"]

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "Ищем в казино", "jobs", allow_delete=False
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert "казино" in (saved.skip_reason or "")


async def test_the_blacklist_reads_the_whole_post(parsing, session_factory):
    """Чёрный список читает весь текст, а не его начало.

    Разбор обрезает объявление под предел модели; образец за обрезкой
    иначе не сработал бы вовсе.
    """
    pipeline, vacancy = parsing
    pipeline.blacklist_patterns = ["казино"]
    long_tail = "а" * 7000 + " казино"

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, long_tail, "jobs", allow_delete=False
    )

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NOT_FIT


async def test_a_blacklisted_post_never_reaches_the_validator(parsing, session_factory):
    """Отсеянное чёрным списком до оценщика не доходит.

    Список — не догадка о посте, а решение человека: с этими не работаем, и
    жанр поста ответа не меняет. Спрашивать о таком посте модель незачем — её
    вердикт ничего не решит, а обращение стоит денег. Этим он и отличается от
    баллов, уехавших за оценщика: те отвечают на вопрос, осмысленный только
    после «это вакансия».
    """
    pipeline, vacancy = parsing
    pipeline.blacklist_patterns = ["казино"]

    await parse.parse_and_update_vacancy(pipeline,
        vacancy.id, "Ищем в казино", "jobs", allow_delete=False
    )

    assert pipeline.validated is False
    assert (await only_row(session_factory, Vacancy)).skip_reason == "blacklist: казино"


async def test_a_rejected_vacancy_carries_the_reason(parsing, session_factory):
    """Отклонённая проверяльщиком вакансия несёт его причину.

    Пользователь читает её в карточке и решает, согласен ли; без
    причины отказ выглядит произволом.
    """
    pipeline, vacancy = parsing
    pipeline.verdict = FitValidation(verdict="reject", reason="нужен C++")

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs")

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "llm: нужен C++"


async def test_a_validator_without_an_answer_means_unfit(parsing, session_factory):
    """Проверяльщик без ответа приравнивается к отказу.

    Модель работает на машине пользователя и отваливается обычным
    делом; откликнуться, ничего не зная о вакансии, хуже, чем нет.
    """
    pipeline, vacancy = parsing
    pipeline.verdict = None

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs")

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "llm: validation unavailable"


async def test_a_verdict_that_never_fits_lands_the_vacancy_for_the_human(
    parsing, session_factory
):
    """Не поместившийся вердикт кладёт строку человеку, а не в вечный круг.

    Объявление к этому мигу разобрано — приговора нет только у пригодности, и
    переспросить с поднятым потолком модель уже пробовала. Оставь мы строку
    неразобранной, подбор брал бы её при каждом запуске и платил полным
    разбором; оставь «новой» — отклик ушёл бы по вакансии, которую никто не
    проверял.
    """
    pipeline, vacancy = parsing
    pipeline.verdict = None
    pipeline.fit_trouble = TRUNCATED_TROUBLE

    done = await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs"
    )

    saved = await only_row(session_factory, Vacancy)
    assert done is True
    assert saved.is_parsed is True
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == TRUNCATED_SKIP_REASON


async def test_a_verdict_nobody_answered_leaves_the_vacancy_unparsed(
    parsing, session_factory
):
    """Вердикт, которого не у кого спросить, оставляет вакансию неразобранной.

    Провайдер лежит целыми пачками — двадцать вакансий подряд уходили при этом
    в «не подходит» с пометкой «вердикт недоступен», и вернуть их могла только
    кнопка по каждой. Неразобранную строку подберёт следующий заход сам.
    """
    pipeline, vacancy = parsing
    pipeline.verdict = None
    pipeline.fit_trouble = "llm_request_error"

    done = await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs"
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.is_parsed is False
    # Чужой приговор из обстановки — на месте: своего разбор не выносил.
    assert saved.skip_reason == "прошлый отказ"
    assert done is False


async def test_trash_from_the_validator_is_thrown_out_on_ingest(
    parsing, session_factory
):
    """Признанное мусором при обычном сборе выбрасывается с отметкой."""
    pipeline, vacancy = parsing
    pipeline.verdict = FitValidation(verdict="trash", reason="это реклама курсов")

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs", allow_delete=True)

    assert await all_rows(session_factory, Vacancy) == []
    assert (await only_row(session_factory, TrashEvent)).reason == (
        "trash: это реклама курсов"
    )


async def test_trash_from_the_validator_is_only_marked_on_a_rerun(
    parsing, session_factory
):
    """Признанное мусором при повторном прогоне остаётся карточкой."""
    pipeline, vacancy = parsing
    pipeline.verdict = FitValidation(verdict="trash", reason="это реклама курсов")

    await parse.parse_and_update_vacancy(pipeline, 
        vacancy.id, "текст", "jobs", allow_delete=False
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "trash: это реклама курсов"


async def test_the_genre_is_asked_before_the_fit(parsing, session_factory):
    """«Вакансия ли это» спрашивают отдельным зовом, до вопроса о пригодности.

    Слитые в один вопрос, они спорят: на посте, похожем на анкету кандидата,
    «подходит ли» перебивает «вакансия ли»: оценщик отвечает «годится» на
    резюме, и письмо уходит живому человеку. Вопрос о жанре задаётся без анкеты вовсе, и похожести взяться
    неоткуда, а пригодность у не-вакансии уже не спрашивают.
    """
    pipeline, vacancy = parsing
    pipeline.genre = PostGenre(is_vacancy=False, reason="автор предлагает себя")

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs", allow_delete=True)

    assert pipeline.genre_asked is True
    assert pipeline.validated is False
    assert await all_rows(session_factory, Vacancy) == []
    mark = await only_row(session_factory, TrashEvent)
    assert mark.reason == "trash: автор предлагает себя"


async def test_a_post_the_genre_call_could_not_judge_stays_unparsed(parsing, session_factory):
    """Не спросившийся жанр приговора не выносит — строка ждёт следующего раза.

    Лежащий провайдер иначе уводил бы в мусор всё, что пришло за это время, а
    удаление необратимо.
    """
    pipeline, vacancy = parsing
    pipeline.genre_trouble = "provider is down"

    done = await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=True
    )

    assert done is False
    assert pipeline.validated is False
    saved = await only_row(session_factory, Vacancy)
    assert saved.is_parsed is False
    assert saved.skip_reason == "прошлый отказ"


async def test_a_genre_answer_that_never_fits_is_handed_to_the_person(
    parsing, session_factory
):
    """Не поместившийся ответ о жанре отдают человеку, а не оставляют навсегда.

    Обрыв по пределу токенов повторится и на втором заходе с запасом: строка
    иначе разбиралась бы заново каждый оборот и не разобралась бы никогда.
    """
    pipeline, vacancy = parsing
    pipeline.genre_trouble = TRUNCATED_TROUBLE

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs", allow_delete=False)

    saved = await only_row(session_factory, Vacancy)
    assert pipeline.validated is False
    assert saved.skip_reason == TRUNCATED_SKIP_REASON


async def test_an_unreadable_genre_answer_lets_the_post_through(parsing, session_factory):
    """Невнятный ответ о жанре приговора не выносит и пропускает пост дальше.

    Удалять по неразобранному ответу нельзя, а следом стоит оценщик — он и
    рассудит. Закрытая дверь тут стоила бы живых вакансий.
    """
    pipeline, vacancy = parsing
    pipeline.genre = None

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs", allow_delete=True)

    assert pipeline.validated is True
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NEW


async def test_a_resume_mark_on_a_rerun_marks_instead_of_deleting(parsing, session_factory):
    """Метка резюме на прогоне заново помечает строку, а не сносит её.

    Кнопку нажал человек, и вакансия не должна исчезнуть у него из-под рук.
    Поля при этом чистятся: разбора не было, и разобранное прошлым заходом
    рядом с приговором «мусор» выдавало бы старое за новое.
    """
    pipeline, vacancy = parsing

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "#cv Позиция: Python Developer", "jobs", allow_delete=False
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == "trash: пост соискателя, метка #cv"
    assert saved.title is None
    assert await all_rows(session_factory, TrashEvent) == []


async def test_the_validator_is_asked_before_the_score(parsing, session_factory):
    """«Это вообще вакансия» спрашивают раньше баллов, а не после.

    Баллы отвечают на другой вопрос — подходит ли вакансия кандидату, — и к
    посту, который вакансией не является, неприменимы вовсе. Стой они первыми,
    резюме получало бы «не набрало порога» и до смыслового приговора не
    доезжало бы. Хуже того, такой отсев выглядит работающим фильтром — а
    резюме, случайно набравшее баллы, получает письмо.
    """
    pipeline, vacancy = parsing
    pipeline.verdict = FitValidation(verdict="trash", reason="это пост соискателя")
    await pipeline.rs.set_app("scoring_threshold", "100")

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs", allow_delete=True)

    assert pipeline.validated is True
    assert await all_rows(session_factory, Vacancy) == []
    mark = await only_row(session_factory, TrashEvent)
    assert mark.reason == "trash: это пост соискателя"


async def test_the_score_judges_only_what_the_validator_called_a_vacancy(
    parsing, session_factory
):
    """Порог остался, но судит только признанное вакансией.

    Оценка по навыкам — про кандидата, а не про пост: она отвечает, стоит ли
    откликаться на эту вакансию. Приговор «не набрала порога» осмыслен только
    после того, как сказано, что перед нами вакансия.
    """
    pipeline, vacancy = parsing
    await pipeline.rs.set_app("scoring_threshold", "100")

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs", allow_delete=False)

    saved = await only_row(session_factory, Vacancy)
    assert pipeline.validated is True
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason.endswith("< 100")
