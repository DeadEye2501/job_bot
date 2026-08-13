"""Бот, каким его видит окно: пять обращений, которые делает мост.

Настоящий `Bot` держит клиента Telegram, два клиента модели и конвейер — а
мост внутрь них не заходит ни разу, он зовёт пять именованных методов и
смотрит на ответ. Подделка повторяет ровно эти пять: остальное поднимать
незачем, а `tests/fakes/ingestion.py` подделывает не бота, а конвейер под ним.
"""


class UiBot:
    """Отвечает заготовленным и помнит, о чём просили."""

    def __init__(
        self,
        *,
        poll: str = "ok",
        rerun: bool = True,
        application: tuple[bool, str] = (True, "sent"),
        forgotten: bool = True,
    ) -> None:
        self._poll = poll
        self._rerun = rerun
        self._application = application
        self._forgotten = forgotten
        self.calls: list[tuple] = []

    async def force_poll_once(self) -> str:
        self.calls.append(("force_poll_once",))
        return self._poll

    def cancel_current_poll(self) -> None:
        self.calls.append(("cancel_current_poll",))

    async def ui_rerun_vacancy_pipeline(self, vacancy_id: int) -> bool:
        self.calls.append(("ui_rerun_vacancy_pipeline", vacancy_id))
        return self._rerun

    async def ui_send_vacancy_application(self, vacancy_id: int) -> tuple[bool, str]:
        self.calls.append(("ui_send_vacancy_application", vacancy_id))
        return self._application

    async def ui_forget_vacancy(self, vacancy_id: int) -> bool:
        self.calls.append(("ui_forget_vacancy", vacancy_id))
        return self._forgotten
