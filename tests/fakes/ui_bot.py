"""Бот, каким его видит окно: обращения, которые делает мост.

Настоящий `Bot` держит клиента Telegram, два клиента модели и конвейер — а
мост внутрь них не заходит ни разу, он зовёт именованные методы и смотрит на
ответ. Подделка повторяет ровно их: остальное поднимать незачем, а
`tests/fakes/ingestion.py` подделывает не бота, а конвейер под ним.
"""

from dataclasses import dataclass

from backend.bot.pasted import PastedOutcome
from backend.bot.rerun import RerunOutcome


@dataclass(frozen=True)
class Sent:
    """Записанное сообщение, каким его читает мост: ему нужен только номер."""

    id: int


ANSWERS = {
    "poll": "ok",
    "rerun": "ok",
    "pasted": "ok",
    "application": (True, "sent"),
    "forgotten": True,
    "read": 1,
    "sent": 1,
    "refusal": None,
    "log_out_refusal": None,
    "channel_poll": "ok",
    "added": (1, "created"),
    "aggregator_run": "ok",
    "aggregator_login": "ok",
    "apply_via": "ok",
    "aggregator_deleted": "ok",
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

    def cancel_round(self) -> None:
        self.calls.append(("cancel_round",))

    def request_stop(self) -> None:
        self.calls.append(("request_stop",))

    def kick(self) -> None:
        self.calls.append(("kick",))

    async def run(self, *, once: bool = False) -> None:
        """Работа бота, которая сразу кончается.

        Мост запускает её на моторе и держит только `Future`; что внутри, ему
        безразлично — важно, что зов есть и что подпись совпадает с настоящей.
        """
        self.calls.append(("run", once))

    async def ui_rerun_vacancy_pipeline(self, vacancy_id: int) -> RerunOutcome:
        self.calls.append(("ui_rerun_vacancy_pipeline", vacancy_id))
        return self.answers["rerun"]

    async def ui_ingest_pasted_text(self, text, posted_at) -> PastedOutcome:
        self.calls.append(("ui_ingest_pasted_text", text, posted_at))
        return self.answers["pasted"]

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

    async def log_out_session(self) -> None:
        self.calls.append(("log_out_session",))
        if self.answers["log_out_refusal"] is not None:
            raise RuntimeError(self.answers["log_out_refusal"])

    async def poll_channel_now(self, channel_id: int) -> str:
        self.calls.append(("poll_channel_now", channel_id))
        return self.answers["channel_poll"]

    async def add_channel(self, username: str) -> tuple[int | None, str]:
        self.calls.append(("add_channel", username))
        return self.answers["added"]

    async def run_aggregator_now(self, aggregator_id: int) -> str:
        self.calls.append(("run_aggregator_now", aggregator_id))
        return self.answers["aggregator_run"]

    async def login_aggregator(self, aggregator_id: int) -> str:
        self.calls.append(("login_aggregator", aggregator_id))
        return self.answers["aggregator_login"]

    async def apply_via_agent(self, vacancy_id: int, way) -> str:
        self.calls.append(("apply_via_agent", vacancy_id, way))
        return self.answers["apply_via"]

    def human_done(self) -> None:
        self.calls.append(("human_done",))

    async def delete_aggregator(self, aggregator_id: int) -> str:
        self.calls.append(("delete_aggregator", aggregator_id))
        return self.answers["aggregator_deleted"]
