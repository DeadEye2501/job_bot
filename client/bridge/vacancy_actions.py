"""Действия над вакансией: перезапуск разбора, отклик, удаление.

Номер вакансии кнопки читают общим `answer.asked_id`: то же чтение стоит у
карточек контакта, и написания у них начали расходиться перехватываемыми
породами.
"""

from __future__ import annotations

from backend.domain.apply_order import Way
from backend.flows.aggregator_apply import vacancy_ways
from backend.models import Vacancy
from backend.repository import vacancies_life
from backend.agent.availability import current_refusal
from client.bridge.answer import Denied, asked_id, denied, launched, reply
from client.bridge.refusals import (
    APPLY_VIA_REFUSALS,
    NO_BOT,
    NO_VACANCY,
    RERUN_REFUSALS,
    SEND_REFUSALS,
    WAY_UNKNOWN,
    agent_refusals,
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

        bot = self._hub.bot
        if bot is None:
            return denied(NO_BOT, vacancy_id=vacancy_id, action="rerun")

        return launched(
            self._hub,
            lambda: bot.ui_rerun_vacancy_pipeline(vacancy_id),
            RERUN_REFUSALS,
            "Вакансия разобрана заново.",
            vacancy_id=vacancy_id,
            action="rerun",
        )

    def apply_ways(self, vacancy_id: int) -> dict:
        """Способы отклика на вакансию для окна выбора, есть ли Telegram и что запирает агента.

        Названий способов мост не отдаёт: таблица названий одна, во фронте.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                await require_vacancy(session, vacancy_id)
                vacancy = await session.get(Vacancy, vacancy_id)
                telegram = vacancy.hr_id is not None
            ways = await vacancy_ways(self._hub.session_factory, vacancy_id, set())
            return {"ways": [{"method": w.method, "target": w.target} for w in ways],
                    "telegram": telegram, "lock": current_refusal(self._hub.rs.chat)}

        return reply(self._hub.runner, run())

    def apply_via(self, payload: dict) -> dict:
        """Откликнуться агентом выбранным способом — он должен быть среди способов вакансии."""
        vacancy_id, refused = asked_id(payload, "vacancy_id", "apply_via")
        if refused is not None:
            return refused
        bot = self._hub.bot
        if bot is None:
            return denied(NO_BOT, vacancy_id=vacancy_id, action="apply_via")
        chosen = (payload.get("method"), payload.get("target"))

        async def run() -> Way:
            async with self._hub.session_factory() as session:
                await require_vacancy(session, vacancy_id)
            ways = await vacancy_ways(self._hub.session_factory, vacancy_id, set())
            way = next((w for w in ways if (w.method, w.target) == chosen), None)
            if way is None:
                raise Denied(WAY_UNKNOWN, vacancy_id=vacancy_id)
            return way

        found = reply(self._hub.runner, run())
        if "ok" not in found:
            return found
        return launched(
            self._hub,
            lambda: bot.apply_via_agent(vacancy_id, found["ok"]),
            agent_refusals(APPLY_VIA_REFUSALS, self._hub.rs.chat),
            "Отклик записан.",
            vacancy_id=vacancy_id,
            action="apply_via",
        )

    def send_application(self, payload: dict) -> dict:
        """Отправить отклик по вакансии: письмо, резюме и всё остальное — на боте.

        Ответ говорит только «пущено»: письмо сочиняет модель, и до её ответа
        зов держал бы окно, а начатую отправку это всё равно не отменило бы.
        """
        vacancy_id, refused = asked_id(payload, "vacancy_id", "send_application")
        if refused is not None:
            return refused

        bot = self._hub.bot
        if bot is None:
            return denied(NO_BOT, vacancy_id=vacancy_id, action="send")

        async def sending() -> str:
            sent, reason = await bot.ui_send_vacancy_application(vacancy_id)
            return "ok" if sent else reason

        return launched(
            self._hub,
            sending,
            SEND_REFUSALS,
            "Отклик отправлен.",
            vacancy_id=vacancy_id,
            action="send",
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
