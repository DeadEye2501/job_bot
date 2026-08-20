"""Экран «Вакансии»: список, карточка и правки в них."""

from __future__ import annotations

import logging

from backend.domain.scoring import build_skill_lookup
from backend.models import Vacancy, VacancyStatus
from backend.repository import (
    profile_skills as skills_repo,
    vacancies_card,
    vacancies_list,
    vacancy_status,
)
from client.bridge.answer import Denied, bad_fields, denied, reply
from client.bridge.hub import Hub
from client.bridge.refusals import NO_VACANCY
from client.bridge.page import read_page
from client.bridge.vacancy_actions import VacancyActions
from client.bridge.vacancy_filter import read_vacancy_filter
from client.bridge.vacancy_links import VacancyLinks
from client.bridge.wire import _vacancy_detail_to_dict, _vacancy_list_row_to_dict


logger = logging.getLogger(__name__)


class Vacancies(VacancyActions, VacancyLinks):
    """Вакансия на своём экране: как её показывают, как правят и что с ней делают.

    Разрезано на три файла по объёму: экран один, и в одном файле он не
    помещается. Разрез при этом не по ответственности — `change_status` отсюда
    и `delete` из примеси зовут один и тот же модуль репозитория, — а по тому,
    что человек делает на экране: смотрит и правит поля здесь, жмёт кнопки
    действий и связывает карточки в примесях рядом.

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
        умолчаниям `VacancyFilter`. Списки для выпадающих меню фильтра берутся
        мимо самого фильтра — иначе любой отбор сжимал бы их до того, что
        уцелело в выдаче.
        """
        # Не-объект сводится к пустоте, а не роняет разбор: отбор — дело окна, и
        # испорченная нагрузка не должна отнимать у человека весь список.
        payload = payload if isinstance(payload, dict) else {}
        page = read_page(payload)
        return reply(self._hub.runner, self._listed(read_vacancy_filter(payload, page)))

    async def _listed(self, filters) -> dict:
        async with self._hub.session_factory() as session:
            rows, has_more = await vacancies_list.list_vacancies(session, filters)
            skills = await skills_repo.list_skills(session)
            activity_by_id = await vacancies_list.list_vacancy_last_activity(
                session, [v.id for v in rows]
            )
            filter_options = await vacancies_list.list_vacancy_filter_options(session)
        matched_set = build_skill_lookup(skills)
        return {
            "vacancies": [
                _vacancy_list_row_to_dict(v, matched_set, activity_by_id) for v in rows
            ],
            "filter_options": filter_options,
            "has_more": has_more,
            "score_threshold": self._hub.rs.scoring_threshold,
        }

    def detail(self, vacancy_id: int) -> dict:
        """Карточка одной вакансии целиком.

        Отдаётся вся — описание, стек, контакты, история статусов, события, — а
        окно рисует из неё то, что показывает сейчас. Так карточка растёт без
        правок моста.
        """

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

    def save_notes(self, payload: dict) -> dict:
        """Записать заметку к вакансии.

        Пустую и состоящую из пробелов репозиторий сводит к пустоте; ответом
        уезжает то, что легло в базу, а не то, что прислали, — окно принимает
        его за исходное состояние поля.
        """
        try:
            vacancy_id = int(payload["vacancy_id"])
            notes = payload.get("notes")
            if notes is not None:
                notes = str(notes)
        except (ValueError, TypeError, KeyError) as e:
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

        Отвечает своим ответом, а не общим для карточки: окну не нужно
        перечитывать её целиком, оно правит одну строку, не теряя набранного.
        """
        try:
            history_id = int(payload["history_id"])
            vacancy_id = int(payload["vacancy_id"])
            explanation = payload.get("explanation")
            if explanation is not None:
                explanation = str(explanation)
        except (ValueError, TypeError, KeyError) as e:
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
                    "Запись истории не найдена.",
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
            explanation = payload.get("explanation")
            if explanation is not None:
                explanation = str(explanation)
            new_status = next(s for s in VacancyStatus if s.value == status_raw)
        except StopIteration:
            return denied("Неверный статус.", vacancy_id=payload.get("vacancy_id"))
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("change_status", e)

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
                    if await session.get(Vacancy, vacancy_id) is None:
                        raise Denied(NO_VACANCY, vacancy_id=vacancy_id)
            return {"vacancy_id": vacancy_id}

        return reply(self._hub.runner, run())
