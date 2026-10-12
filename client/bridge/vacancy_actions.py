"""Действия над вакансией: перезапуск разбора, отклик, удаление.

Номер вакансии кнопки читают общим `answer.asked_id`: то же чтение стоит у
карточек контакта, и написания у них начали расходиться перехватываемыми
породами.
"""

from __future__ import annotations

from backend.applying.world import available_ways
from backend.domain.apply_order import Way
from backend.repository import vacancies_life
from client.bridge.answer import Denied, asked_id, launched_on_bot, reply
from client.bridge.refusals import (
    APPLY_VIA_REFUSALS,
    NO_VACANCY,
    RERUN_REFUSALS,
    WAY_UNKNOWN,
)
from client.bridge.vacancy_links import require_vacancy


class VacancyActions:
    """Кнопки карточки вакансии — то, что меняет её судьбу, а не вид.

    Собирающий обязан держать `_hub`: из него берутся мотор, сессии и бот.
    """

    def rerun(self, payload: dict) -> dict:
        """Прогнать разбор вакансии моделью заново.

        Ответ говорит только «пущено»: разбор — это от двух до пяти обращений к
        модели, и ждать их значит держать зов вместе с окном. Чем кончилось,
        человек узнаёт вестью, а карточка перечитывается сама по вести о смене
        списка.
        """
        vacancy_id, refused = asked_id(payload, "vacancy_id", "rerun")
        if refused is not None:
            return refused

        return launched_on_bot(
            self._hub,
            lambda bot: bot.ui_rerun_vacancy_pipeline(vacancy_id),
            RERUN_REFUSALS,
            "Вакансия разобрана заново.",
            vacancy_id=vacancy_id,
            action="rerun",
        )

    def apply_ways(self, vacancy_id: int) -> dict:
        """Доступные сейчас способы отклика на вакансию для окна выбора.

        Названий способов мост не отдаёт: таблица названий одна, во фронте.
        Недоступного способа в перечне нет вовсе — объяснять запор нечего.
        """

        async def run() -> dict:
            ways = await self._available_ways(vacancy_id)
            return {"ways": [{"method": w.method, "target": w.target} for w in ways]}

        return reply(self._hub.runner, run())

    async def _available_ways(self, vacancy_id: int) -> list[Way]:
        async with self._hub.session_factory() as session:
            await require_vacancy(session, vacancy_id)
        return await available_ways(self._hub.rs, self._hub.session_factory, vacancy_id)

    def apply_via(self, payload: dict) -> dict:
        """Откликнуться выбранным способом — он должен быть среди доступных способов вакансии."""
        vacancy_id, refused = asked_id(payload, "vacancy_id", "apply_via")
        if refused is not None:
            return refused
        chosen = (payload.get("method"), payload.get("target"))

        async def run() -> Way:
            ways = await self._available_ways(vacancy_id)
            way = next((w for w in ways if (w.method, w.target) == chosen), None)
            if way is None:
                raise Denied(WAY_UNKNOWN, vacancy_id=vacancy_id)
            return way

        found = reply(self._hub.runner, run())
        if "ok" not in found:
            return found
        return launched_on_bot(
            self._hub,
            lambda bot: bot.apply_chosen_way(vacancy_id, found["ok"]),
            APPLY_VIA_REFUSALS,
            "Отклик записан.",
            vacancy_id=vacancy_id,
            action="apply_via",
        )

    def delete(self, payload: dict) -> dict:
        """Снести вакансию вместе с историей и событиями."""
        vacancy_id, refused = asked_id(payload, "vacancy_id", "delete")
        if refused is not None:
            return refused

        async def run() -> dict:
            # Через конвейер, а не прямо в репозиторий: вместе со строкой уходит
            # её вектор из кэша отсева перепостов. Без бота кэша нет вовсе —
            # тогда довольно строки.
            bot = self._hub.bot
            if bot is not None:
                gone = await bot.ui_forget_vacancy(vacancy_id)
            else:
                async with self._hub.session_factory() as session:
                    async with session.begin():
                        gone = await vacancies_life.delete_vacancy(session, vacancy_id)
            if not gone:
                raise Denied(NO_VACANCY, vacancy_id=vacancy_id, action="delete")
            return {"vacancy_id": vacancy_id, "action": "delete"}

        return reply(self._hub.runner, run())
