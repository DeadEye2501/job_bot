"""Экран «Вакансии»: список, карточка и правки в них."""

from __future__ import annotations

import logging
from functools import partial

from backend.domain.hosts import typed_page
from backend.domain.scoring import build_skill_lookup
from backend.models import VacancyStatus
from backend.repository import (
    applications,
    profile_skills as skills_repo,
    vacancies_card,
    vacancies_list,
    vacancy_status,
)
from backend.flows import hand_made
from backend.flows.hand_made import HandRequest
from backend.incoming import moment_or_none, text_or_none
from client.bridge.answer import (
    BAD_PAYLOAD,
    Denied,
    bad_fields,
    denied,
    finished,
    launched_on_bot,
    reply,
)
from client.bridge.events import LIST_CHANGED
from client.bridge.form_payloads import read_new_vacancy_fields
from client.bridge.hub import Hub
from client.bridge.refusals import (
    NAME_REQUIRED,
    NO_VACANCY,
    PASTED_REFUSALS,
    TEXT_REQUIRED,
    URL_REQUIRED,
    agent_refusals,
)
from client.bridge.page import read_page
from client.bridge.vacancy_actions import VacancyActions, forgotten
from client.bridge.vacancy_contacts import VacancyContacts
from client.bridge.vacancy_filter import read_vacancy_filter
from client.bridge.vacancy_links import VacancyLinks, require_vacancy
from client.bridge.wire import (
    _screening_to_dict,
    _vacancy_detail_to_dict,
    _vacancy_list_row_to_dict,
)


logger = logging.getLogger(__name__)


def _typed_text(raw) -> str | None:
    """Набранное человеком, каким оно пришло; пустота значит «поле не прислали».

    От `text_or_none` отличается тем, что пустую строку не сводит к пустоте:
    стёртая заметка — это правка, и записать её надо, а «не прислали» значит
    «не трогать». Тремя слотами это было написано одинаково, дважды побайтно.
    """
    return None if raw is None else str(raw)


class Vacancies(VacancyActions, VacancyLinks, VacancyContacts):
    """Вакансия на своём экране: как её показывают, как правят и что с ней делают.

    Разрезано на четыре файла по объёму: экран один, и в одном файле он не
    помещается. Разрез при этом не по ответственности — `change_status` отсюда
    и `delete` из примеси зовут один и тот же модуль репозитория, — а по тому,
    что человек делает на экране: смотрит и правит поля здесь, жмёт кнопки
    действий, связывает карточки и правит контакты в примесях рядом.

    Поверхность у страницы одна, `api.vacancies`: примесь здесь раскладывает
    один экран по файлам, а не готовит вторую реализацию.
    """

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def list(self, payload: dict | None = None) -> dict:
        """Список вакансий с отбором, поиском и порядком на стороне базы.

        Форма строки — `wire._vacancy_list_row_to_dict`. Каждый пункт стека
        помечен ``matched``, если он есть в навыках и псевдонимах анкеты: так
        окно подсвечивает нужные чипы, не спрашивая навыки отдельно.

        Нагрузка — объект с полями отбора; пустая или негодная сводится к
        умолчаниям `VacancyFilter`.
        """
        # Не-объект сводится к пустоте, а не роняет разбор: отбор — дело окна, и
        # испорченная нагрузка не должна отнимать у человека весь список.
        payload = payload if isinstance(payload, dict) else {}
        page = read_page(payload)
        return reply(self._hub.runner, self._listed(read_vacancy_filter(payload, page)))

    def filter_options(self) -> dict:
        """Перечни для выпадающих меню фильтра: все каналы и все компании.

        Своим зовом, а не полем списка. От отбора они не зависят — иначе любой
        отбор сжимал бы меню до того, что уцелело в выдаче, — а список окно
        перечитывает на каждое нажатие клавиши в поиске: приезжай перечни с
        ним, каждый набранный знак стоил бы лишнего полного прохода по таблице
        вакансий.

        Спрашивают их при открытии экрана и на вести о правке списка: новая
        вакансия приносит с собой и новую компанию, и новый канал.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                options = await vacancies_list.list_vacancy_filter_options(session)
            return {"filter_options": options}

        return reply(self._hub.runner, run())

    async def _listed(self, filters) -> dict:
        async with self._hub.session_factory() as session:
            rows, has_more = await vacancies_list.list_vacancies(session, filters)
            skills = await skills_repo.list_skills(session)
            activity_by_id = await vacancies_list.list_vacancy_last_activity(
                session, [v.id for v in rows]
            )
        matched_set = build_skill_lookup(skills)
        return {
            "vacancies": [
                _vacancy_list_row_to_dict(v, matched_set, activity_by_id) for v in rows
            ],
            "has_more": has_more,
            "score_threshold": self._hub.rs.scoring_threshold,
        }

    def detail(self, vacancy_id) -> dict:
        """Карточка одной вакансии целиком.

        Отдаётся вся — описание, стек, контакты, история статусов, события, — а
        окно рисует из неё то, что показывает сейчас. Так карточка растёт без
        правок моста.

        Номер приводится, а не принимается на веру: приезжает он нагрузкой, как
        и всё прочее, и негодный уехал бы в запрос к базе — а оттуда вернулся бы
        «вакансии нет», то есть отказ не про то, что случилось.
        """
        try:
            vacancy_id = int(vacancy_id)
        except (ValueError, TypeError) as e:
            return bad_fields("detail", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                detail = await vacancies_card.get_vacancy_detail(session, vacancy_id)
                skills = await skills_repo.list_skills(session)
            if detail is None:
                logger.warning("vacancy_id=%d not found on detail load", vacancy_id)
                raise Denied(NO_VACANCY, vacancy_id=vacancy_id)
            matched_set = build_skill_lookup(skills)
            return {
                "vacancy": _vacancy_detail_to_dict(
                    detail, matched_set, self._hub.rs.scoring_threshold,
                ),
            }

        return reply(self._hub.runner, run())

    def screening(self, vacancy_id: int) -> dict:
        """Скрининг вакансии для окна диалога: отклик за откликом, реплики по порядку."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                await require_vacancy(session, vacancy_id)
                shown = await applications.vacancy_screening(session, vacancy_id)
            return {"applications": [_screening_to_dict(one) for one in shown]}

        return reply(self._hub.runner, run())

    def save_notes(self, payload: dict) -> dict:
        """Записать заметку к вакансии.

        Пустую и состоящую из пробелов репозиторий сводит к пустоте; ответом
        уезжает то, что легло в базу, а не то, что прислали, — окно принимает
        его за исходное состояние поля.
        """
        try:
            vacancy_id = int(payload["vacancy_id"])
            notes = _typed_text(payload.get("notes"))
        except BAD_PAYLOAD as e:
            return bad_fields("save_notes", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    saved = await vacancies_card.update_vacancy_notes(
                        session, vacancy_id, notes
                    )
                    persisted = saved.notes if saved is not None else None
            if saved is None:
                raise Denied(NO_VACANCY, vacancy_id=vacancy_id)
            return {"vacancy_id": vacancy_id, "notes": persisted}

        return reply(self._hub.runner, run())

    def save_history_explanation(self, payload: dict) -> dict:
        """Правка пояснения к одной строке истории статусов.

        Отвечает своим ответом, а не карточкой целиком. Перечитывает её окно
        всё равно — мост дописывает к пояснению точку, и записанное отличается
        от набранного, — но по своему доводу и своим зовом: ответ здесь говорит
        только «легло», и по нему строка истории вспыхивает зелёным.
        """
        try:
            history_id = int(payload["history_id"])
            vacancy_id = int(payload["vacancy_id"])
            explanation = _typed_text(payload.get("explanation"))
        except BAD_PAYLOAD as e:
            return bad_fields("save_history_explanation", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    row = await vacancy_status.update_status_history_explanation(
                        session, history_id, explanation,
                    )
                    saved = row.explanation if row is not None else None
            if row is None:
                logger.warning(
                    "history_id=%d not found (vacancy=%d)", history_id, vacancy_id,
                )
                raise Denied(
                    "Запись истории не найдена",
                    history_id=history_id,
                    vacancy_id=vacancy_id,
                )
            return {
                "vacancy_id": vacancy_id,
                "history_id": history_id,
                "explanation": saved,
            }

        return reply(self._hub.runner, run())

    def change_status(self, payload: dict) -> dict:
        """Записать новое положение дел и строку в историю.

        Положение приходит значением перечня («New», «In Progress»), а не именем
        класса оформления.
        """
        try:
            vacancy_id = int(payload["vacancy_id"])
            status_raw = str(payload["status"]).strip()
            explanation = _typed_text(payload.get("explanation"))
        except BAD_PAYLOAD as e:
            return bad_fields("change_status", e)
        try:
            new_status = VacancyStatus(status_raw)
        except ValueError:
            return denied("Неверный статус", vacancy_id=vacancy_id)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    row = await vacancy_status.change_vacancy_status(
                        session,
                        vacancy_id=vacancy_id,
                        new_status=new_status,
                        explanation=explanation,
                    )
            # Репозиторий отвечает пустотой и на «вакансии нет», и на «ничего не
            # изменилось» — то же положение с пустым пояснением. Различаем сами.
            if row is None:
                async with self._hub.session_factory() as session:
                    await require_vacancy(session, vacancy_id)
            self._hub.events.add(LIST_CHANGED)
            return {"vacancy_id": vacancy_id}

        return reply(self._hub.runner, run())

    def create(self, payload: dict) -> dict:
        """Завести вакансию руками — из окна «Добавить вакансию».

        Для найденного не в Telegram, а глазами: на бирже, в почте, по
        наводке. Конвейер такую не принесёт никогда, а вести её по воронке
        человеку надо тем же экраном.

        Номер заведённой едет ответом тем же полем, каким отвечает заведение
        человека и компании; список окно перечитывает следом само. Повтор по
        «Ссылке на объявление» отвечает номером существующей с `created: false`
        и фразой из набора отказов: доставить её окну иначе нечем.

        С включённым переключателем «Отклик при создании» поля заводит бот:
        отклик идёт через место прогона. Ответ тогда — «пущено», итог — вестью.

        Заслон здесь, а не в репозитории: пустое название — это про форму, а
        не про строку, и отвечать на него надо словами человеку.
        """
        try:
            fields = read_new_vacancy_fields(payload)
        except BAD_PAYLOAD as e:
            return bad_fields("vacancies.create", e)
        if not fields["title"]:
            return denied(NAME_REQUIRED, action="create_vacancy")

        if bool(payload.get("hands_over")):
            return launched_on_bot(
                self._hub,
                lambda bot: bot.ui_ingest_pasted_text(HandRequest("fields", fields, None, True)),
                PASTED_REFUSALS,
                FILED,
                action=HAND_MADE_ACTION,
            )

        async def run() -> dict:
            known = await hand_made.known_at(
                self._hub.session_factory, typed_page(fields["source_url"]), partial(forgotten, self._hub))
            if known is not None:
                return {"action": "create_vacancy", "created_id": known, "created": False,
                        "message": PASTED_REFUSALS["duplicate"]}
            vacancy_id = await hand_made.file_fields(self._hub.session_factory, fields)
            self._hub.events.add(LIST_CHANGED)
            return {"action": "create_vacancy", "created_id": vacancy_id, "created": True, "message": FILED}

        return reply(self._hub.runner, run())

    def create_from_text(self, payload: dict) -> dict:
        """Завести вакансию по вставленному тексту объявления или по ссылке на него.

        Вторая и третья вкладки того же окна: человек приносит текст или
        ссылку, а поля достаёт конвейер — тем же разбором, каким он читает пост
        канала. Что за ссылкой — пост, статья, страница, — решает бот, один раз;
        мост отдаёт её как есть. Набирать то же самое руками значило бы делать
        работу, которую бот делает лучше.

        Ответ говорит только «пущено»: разбор — это несколько обращений к
        модели, и ждать их значит держать окно. Чем кончилось, человек узнаёт
        вестью. Положение переключателя приходит видимым, как его видит
        человек: запертый показан выключенным и выключенным уходит. Страницу
        читает агент, и отказ без него говорит, чего не хватает (`agent_refusals`).
        """
        hands_over = bool(payload.get("hands_over"))
        if "url" in payload:
            url = text_or_none(payload.get("url"))
            if not url:
                return denied(URL_REQUIRED, action=HAND_MADE_ACTION)
            request = HandRequest("link", url, None, hands_over)
        else:
            text = text_or_none(payload.get("raw_text"))
            if not text:
                return denied(TEXT_REQUIRED, action=HAND_MADE_ACTION)
            request = HandRequest("text", text, moment_or_none(payload.get("posted_at")), hands_over)
        return launched_on_bot(
            self._hub,
            lambda bot: bot.ui_ingest_pasted_text(request),
            agent_refusals(PASTED_REFUSALS, self._hub.rs.chat),
            FILED,
            action=HAND_MADE_ACTION,
        )


HAND_MADE_ACTION = "create_from_text"
"""Метка вестей ручного заведения: одна на все вкладки окна, по ней окно ждёт свою."""

FILED = "Вакансия заведена"


def tell_hand_made(events, result) -> None:
    """Итог ручного заведения окну — вестью исхода с меткой и номером вакансии.

    По номеру окно переходит на существующую при повторе.
    """
    finished(
        events, result.outcome, PASTED_REFUSALS, FILED,
        action=HAND_MADE_ACTION, outcome=result.outcome, vacancy_id=result.vacancy_id,
    )
