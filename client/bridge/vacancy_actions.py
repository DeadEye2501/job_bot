"""Действия над вакансией: перезапуск разбора, отклик, удаление."""

from __future__ import annotations

from backend.repository import vacancies_life
from client.bridge.answer import Denied, bad_fields, reply
from client.bridge.refusals import NO_BOT, NO_VACANCY


# Коды отказа конвейера — словами человеку. Совпадает с тем, чем отвечают
# `IngestionPipeline.send_application_for_vacancy` и `Bot.send`: иначе человек не
# отличит настоящую отправку от запрета, отсутствия резюме и поломки модели.
SEND_REFUSALS = {
    "no_vacancy": NO_VACANCY,
    "no_hr": "К вакансии не привязан HR.",
    "already_applied": "Отклик по этой вакансии уже отправлен.",
    "profile_empty": "Профиль пуст — нечем заполнить cover letter.",
    "cover_letter_failed": "Cover letter не прошёл проверку (длина / формат — см. логи).",
    "cv_missing": "Файл резюме не найден — проверьте путь в настройках.",
    "blocked": "Отправка заблокирована (OFF mode / blacklist / у HR нет ни id, ни @username).",
    "telegram_error": "Telegram отказался принять сообщение (см. логи).",
    "race": "Статус вакансии успел измениться — отправка отменена.",
}


class VacancyActions:
    """Кнопки карточки вакансии — то, что меняет её судьбу, а не вид.

    Собирающий обязан держать `_hub`: из него берутся мотор, сессии и бот.
    """

    def rerun(self, payload: dict) -> dict:
        """Прогнать разбор вакансии моделью заново."""
        try:
            vacancy_id = int(payload["vacancy_id"])
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("rerun", e)

        async def run() -> dict:
            bot = self._hub.bot
            if bot is None:
                raise Denied(NO_BOT, vacancy_id=vacancy_id, action="rerun")
            if not await bot.ui_rerun_vacancy_pipeline(vacancy_id):
                raise Denied(
                    "Не удалось перезапустить парсинг "
                    "(нет вакансии или пустой raw_text).",
                    vacancy_id=vacancy_id,
                    action="rerun",
                )
            return {"vacancy_id": vacancy_id, "action": "rerun"}

        return reply(self._hub.runner, run())

    def send_application(self, payload: dict) -> dict:
        """Отправить отклик по вакансии: письмо, резюме и всё остальное — на боте."""
        try:
            vacancy_id = int(payload["vacancy_id"])
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("send_application", e)

        async def run() -> dict:
            bot = self._hub.bot
            if bot is None:
                raise Denied(NO_BOT, vacancy_id=vacancy_id, action="send")
            sent, reason = await bot.ui_send_vacancy_application(vacancy_id)
            if not sent:
                raise Denied(
                    SEND_REFUSALS.get(reason, f"Не удалось отправить: {reason}"),
                    vacancy_id=vacancy_id,
                    action="send",
                )
            return {"vacancy_id": vacancy_id, "action": "send", "reason": reason}

        return reply(self._hub.runner, run())

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
