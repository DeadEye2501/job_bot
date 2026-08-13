"""Бот, каким его видит окно: обращения, которые делает мост.

Настоящий `Bot` держит клиента Telegram, два клиента модели и конвейер — а
мост внутрь них не заходит ни разу, он зовёт именованные методы и смотрит на
ответ. Подделка повторяет ровно их: остальное поднимать незачем, а
`tests/fakes/ingestion.py` подделывает не бота, а конвейер под ним.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Sent:
    """Записанное сообщение, каким его читает мост: ему нужен только номер."""

    id: int


ANSWERS = {
    "poll": "ok",
    "rerun": True,
    "application": (True, "sent"),
    "forgotten": True,
    "read": 1,
    "sent": 1,
    "refusal": None,
    "channel_poll": "ok",
    "cursor_reset": True,
    "detached": 0,
    "added": (1, "created"),
}


class UiBot:
    """Отвечает заготовленным и помнит, о чём просили.

    Ответы приходят словарём поверх умолчаний — тем же приёмом, что у фабрик
    записей. Неизвестное имя отбивается: молча пропусти опечатку, и тест
    зеленел бы на умолчании вместо заказанного ответа.
    """

    def __init__(self, **answers) -> None:
        unknown = set(answers) - set(ANSWERS)
        if unknown:
            raise ValueError(f"UiBot не знает таких ответов: {sorted(unknown)}")
        self.answers = ANSWERS | answers
        self.calls: list[tuple] = []

    def _refuse_if_asked(self) -> None:
        if self.answers["refusal"] is not None:
            raise RuntimeError(self.answers["refusal"])

    async def force_poll_once(self) -> str:
        self.calls.append(("force_poll_once",))
        return self.answers["poll"]

    def cancel_current_poll(self) -> None:
        self.calls.append(("cancel_current_poll",))

    async def ui_rerun_vacancy_pipeline(self, vacancy_id: int) -> bool:
        self.calls.append(("ui_rerun_vacancy_pipeline", vacancy_id))
        return self.answers["rerun"]

    async def ui_send_vacancy_application(self, vacancy_id: int) -> tuple[bool, str]:
        self.calls.append(("ui_send_vacancy_application", vacancy_id))
        return self.answers["application"]

    async def ui_forget_vacancy(self, vacancy_id: int) -> bool:
        self.calls.append(("ui_forget_vacancy", vacancy_id))
        return self.answers["forgotten"]

    async def mark_hr_chat_read(self, hr_id: int) -> int:
        self.calls.append(("mark_hr_chat_read", hr_id))
        return self.answers["read"]

    async def send_to_hr_chat(self, hr_id: int, text: str) -> Sent:
        self.calls.append(("send_to_hr_chat", hr_id, text))
        self._refuse_if_asked()
        return Sent(id=self.answers["sent"])

    async def send_to_hr_media(self, hr_id: int, file_path: str) -> Sent:
        self.calls.append(("send_to_hr_media", hr_id, file_path))
        self._refuse_if_asked()
        return Sent(id=self.answers["sent"])

    async def poll_channel_now(self, channel_id: int) -> str:
        self.calls.append(("poll_channel_now", channel_id))
        return self.answers["channel_poll"]

    async def reset_channel_cursor(self, channel_id: int) -> bool:
        self.calls.append(("reset_channel_cursor", channel_id))
        return self.answers["cursor_reset"]

    async def delete_channel(self, channel_id: int) -> int | None:
        self.calls.append(("delete_channel", channel_id))
        return self.answers["detached"]

    async def add_channel(self, username: str) -> tuple[int | None, str]:
        self.calls.append(("add_channel", username))
        return self.answers["added"]
