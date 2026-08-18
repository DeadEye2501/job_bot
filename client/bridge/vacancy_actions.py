"""Действия над вакансией: перезапуск разбора, отклик, удаление."""

from __future__ import annotations

from backend.repository import vacancies_life
from client.bridge.answer import Denied, bad_fields, denied, launched, reply
from client.bridge.refusals import (
    NO_BOT,
    NO_VACANCY,
    RERUN_REFUSALS,
    SEND_REFUSALS,
)


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
        try:
            vacancy_id = int(payload["vacancy_id"])
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("rerun", e)

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

    def send_application(self, payload: dict) -> dict:
        """Отправить отклик по вакансии: письмо, резюме и всё остальное — на боте.

        Ответ говорит только «пущено»: письмо сочиняет модель, и до её ответа
        зов держал бы окно, а начатую отправку это всё равно не отменило бы.
        """
        try:
            vacancy_id = int(payload["vacancy_id"])
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("send_application", e)

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
        try:
            vacancy_id = int(payload["vacancy_id"])
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("delete", e)

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
