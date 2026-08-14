"""Порядок первого запуска: чем он продолжается и когда он кончен."""

from __future__ import annotations

from client.bridge.answer import reply
from client.bridge.hub import Hub
from client.bridge.lifespan import start_bot
from client.bridge.wire import _llm_provider_to_dict, _tg_creds_to_dict


class Wizard:
    """Первый запуск, каким его видит страница.

    Своего у мастера только это: какие шаги позади и закончена ли установка.
    Сами шаги он делает теми же доменами, что и настроенное приложение, — вход
    в Telegram у `settings`, проверка и запись модели там же, выбор резюме у
    `profile`. Пока поверхностей было две, каждый шаг был написан дважды, и
    слова отказа у двух написаний разъезжались молча.

    Собирающий обязан держать `_hub`: оттуда берутся мотор и настройки.

    Секреты: снимок отдаёт открытым текстом ключ доступа к модели, `api_hash` и
    **облачный пароль Telegram**. Довод общий со снимком настроек: страница
    живёт своим окном и в сеть не выходит. Пароль — то, чем этот снимок от
    соседнего отличается: настройки отдают про него только «есть или нет»
    (`has_password`), потому что там его перенабирают, а здесь человек
    возвращается на прерванный шаг и должен увидеть введённое.
    """

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def state(self) -> dict:
        """С чего продолжать: пройденные шаги и всё, что по ним уже введено.

        Мастер проходят не за один присест — его закрывают и открывают назавтра.
        Не назови мост пройденное, человек вводил бы учётную запись и модель
        заново поверх уже записанных.
        """

        async def run() -> dict:
            rs = self._hub.rs
            tg = rs.tg
            return {
                "completed": _steps_behind(rs),
                "wizard_completed": rs.wizard_completed,
                "tg": {
                    **_tg_creds_to_dict(tg),
                    "password": tg.password if tg else "",
                },
                "chat": _llm_provider_to_dict(rs.chat),
                "embed": _llm_provider_to_dict(rs.embed),
                "cv_path": rs.cv_path,
            }

        return reply(self._hub.runner, run())

    def skip_cv(self) -> dict:
        """Пройти шаг резюме, не приложив файла.

        Отклик уйдёт и без вложения — письмо важнее файла. Записанный путь при
        этом стирается: человек мог выбрать файл и передумать, а оставленный
        путь ушёл бы с первым же откликом.
        """

        async def run() -> dict:
            await self._hub.rs.set_app("cv_path", "")
            return {"cv_path": ""}

        return reply(self._hub.runner, run())

    def complete(self) -> dict:
        """Отметить установку законченной и поднять бота под настроенным.

        Отметка решает, что покажет следующий запуск. Ставится она последним
        шагом, а не первым: брось человек мастер посередине, следующий запуск
        обязан открыть его там же, а не пустить в ненастроенное приложение.

        Бот поднимается здесь же, потому что раньше было нечем: окно открылось
        на пустых настройках, а вход на первом шаге застал приложение без
        моделей. Не подними его тут, человек прошёл бы мастер до конца и
        оказался в приложении, где не идёт сбор, — до следующего запуска.
        """

        async def run() -> dict:
            await self._hub.rs.mark_wizard_completed()
            return {"wizard_completed": True}

        answer = reply(self._hub.runner, run())
        if "ok" in answer:
            start_bot(self._hub)
        return answer


def _steps_behind(rs) -> list[int]:
    """Какие шаги мастера уже пройдены, судя по записанному.

    Первый шаг засчитывается по строке сеанса, а не по учётным данным: данные
    вводят до кода подтверждения, а подключиться бот сможет только с сеансом.

    Четвёртый — по пути к резюме либо по отметке о законченной установке:
    пропустивший резюме оставляет путь пустым нарочно, и отличить его от
    недошедшего можно только отметкой.
    """
    completed: list[int] = []
    if rs.has_tg_session:
        completed.append(1)
    if rs.chat is not None:
        completed.append(2)
    if rs.embed is not None:
        completed.append(3)
    if rs.cv_path or rs.wizard_completed:
        completed.append(4)
    return completed
