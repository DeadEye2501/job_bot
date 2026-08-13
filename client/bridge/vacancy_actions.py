"""Действия над вакансией: перезапуск разбора, отклик, удаление."""

from __future__ import annotations

import json

from PySide6.QtCore import Signal, Slot

from backend.repository import vacancies_life
from client.bridge.answer import _err, _ok
from client.bridge.payload import _log_invalid_payload


class VacancyActionSlots:
    """Кнопки карточки вакансии — то, что меняет её судьбу, а не вид.

    Подмешивающий обязан держать `_bot`, `_session_factory` и `_dispatch`.
    """

    vacancy_action_done = Signal(str)

    @Slot(str)
    def rerun_vacancy_pipeline(self, payload_json: str) -> None:
        """Прогнать разбор вакансии моделью заново — кнопка «Прогнать заново»."""
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("rerun_vacancy_pipeline", e)
            self.vacancy_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.")
            ok = await self._bot.ui_rerun_vacancy_pipeline(vacancy_id)
            if not ok:
                return _err(
                    "Не удалось перезапустить парсинг (нет вакансии или пустой raw_text).",
                    vacancy_id=vacancy_id,
                    action="rerun",
                )
            return _ok({"vacancy_id": vacancy_id, "action": "rerun"})

        self._dispatch(self.vacancy_action_done, run())

    @Slot(str)
    def send_vacancy_application(self, payload_json: str) -> None:
        """Manual cover-letter send для конкретной вакансии — кнопка
        «Отправить отклик». Backend сам генерит письмо, прикрепляет резюме
        и шлёт связанному HR. Skip-причины пробрасываются в UI как
        конкретные сообщения, иначе юзер не отличит реальную отправку от
        SEND_LOCKED / отсутствия CV / поломки LLM."""
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("send_vacancy_application", e)
            self.vacancy_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        # Skip-коды → human-readable. Совпадает с тем, что emit'ит
        # IngestionPipeline.send_application_for_vacancy и Bot.send.
        REASONS = {
            "no_vacancy":         "Вакансия не найдена.",
            "no_hr":              "К вакансии не привязан HR.",
            "already_applied":    "Отклик по этой вакансии уже отправлен.",
            "profile_empty":      "Профиль пуст — нечем заполнить cover letter.",
            "cover_letter_failed":"Cover letter не прошёл проверку (длина / формат — см. логи).",
            "cv_missing":         "Файл резюме не найден — проверьте путь в настройках.",
            "blocked":            "Отправка заблокирована (OFF mode / blacklist / у HR нет ни id, ни @username).",
            "telegram_error":     "Telegram отказался принять сообщение (см. логи).",
            "race":               "Статус вакансии успел измениться — отправка отменена.",
        }
        # Success-коды тоже доходят до UI на случай будущих кодов
        # (sent — единственный сейчас, note=None → toast не показываем,
        # UI сам нарисует обычный success).
        SUCCESS_NOTES = {
            "sent":               None,
        }

        async def run() -> str:
            if self._bot is None:
                return _err("Бот ещё не готов.")
            ok, reason = await self._bot.ui_send_vacancy_application(vacancy_id)
            if not ok:
                msg = REASONS.get(reason, f"Не удалось отправить: {reason}")
                return _err(msg, vacancy_id=vacancy_id, action="send")
            payload = {"vacancy_id": vacancy_id, "action": "send", "reason": reason}
            note = SUCCESS_NOTES.get(reason)
            if note is not None:
                payload["note"] = note
            return _ok(payload)

        self._dispatch(self.vacancy_action_done, run())

    @Slot(str)
    def delete_vacancy(self, payload_json: str) -> None:
        """Hard-delete vacancy + history/events; nulls message.vacancy_id."""
        try:
            payload = json.loads(payload_json)
            vacancy_id = int(payload["vacancy_id"])
        except (ValueError, TypeError, KeyError) as e:
            _log_invalid_payload("delete_vacancy", e)
            self.vacancy_action_done.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            # Через конвейер, а не прямо в репозиторий: вместе со строкой
            # уходит её вектор из кэша отсева перепостов. Без бота кэша нет
            # вовсе — тогда довольно строки.
            if self._bot is not None:
                ok = await self._bot.ui_forget_vacancy(vacancy_id)
            else:
                async with self._session_factory() as session:
                    async with session.begin():
                        ok = await vacancies_life.delete_vacancy(session, vacancy_id)
            if not ok:
                return _err(
                    "Вакансия не найдена.",
                    vacancy_id=vacancy_id,
                    action="delete",
                )
            return _ok({"vacancy_id": vacancy_id, "action": "delete"})

        self._dispatch(self.vacancy_action_done, run())
