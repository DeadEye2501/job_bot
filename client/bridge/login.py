"""Вход в Telegram: три шага, общие основному окну и мастеру."""

from __future__ import annotations

from backend.telegram_login import LoginStep
from client.bridge.answer import BAD_PAYLOAD, Denied, bad_fields, reply
from client.bridge.refusals import CODE_FIRST, CODE_STEP_FIRST


def read_credentials(payload: dict) -> tuple[int, str, str]:
    """Учётные данные из формы входа: номер приложения, ключ и телефон.

    Номер приложения приводится к числу здесь: из окна всё приезжает текстом, а
    Telegram ждёт число. Уйди он строкой — библиотека отказала бы уже на
    соединении, и человек увидел бы поломку вместо понятного «проверьте api_id».
    """
    return (
        int(payload["api_id"]),
        str(payload["api_hash"]).strip(),
        str(payload["phone"]).strip(),
    )


def read_code(payload: dict) -> str:
    """Код подтверждения из формы."""
    return str(payload["code"]).strip()


def read_password(payload: dict) -> str:
    """Облачный пароль ровно тем, что набрали.

    Ни обрезки пробелов, ни приведения регистра: сверяет пароль Telegram, и
    любая правка по дороге обернулась бы необъяснимым отказом на верном.
    """
    return str(payload["password"])


async def code_step(login, code: str) -> LoginStep:
    """Второй шаг с заслоном: код, введённый до запроса, дальше не идёт.

    Окно может остаться открытым с прошлой попытки, а попытка к тому времени
    уже закрыта. Уйди код в закрытую попытку — ответом была бы поломка
    библиотеки вместо понятного «сначала запросите код».
    """
    if not login.awaiting_code:
        return LoginStep(error=CODE_FIRST)
    return await login.confirm_code(code)


async def password_step(login, password: str) -> LoginStep:
    """Третий шаг с заслоном: пароль до шага с кодом не принимают.

    Пароль спрашивают не всегда — только если он включён у учётной записи.
    Прими его мост раньше времени, он ушёл бы в попытку, которая его не ждёт, и
    потерялся бы молча.
    """
    if not login.awaiting_password:
        return LoginStep(error=CODE_STEP_FIRST)
    return await login.confirm_password(password)


async def step_payload(step_coro) -> dict:
    """Исход шага возвратом: нагрузка — ответом, отказ Telegram — броском.

    Отказы входа предметные, и чинятся они по-разному: неверный код
    перенабирают, за устаревшим идут заново. Своди мост их к общему «не
    получилось» — человек не понял бы, что делать.
    """
    step = await step_coro
    if step.error is not None:
        raise Denied(step.error)
    return step.payload or {}


class Login:
    """Три шага входа в Telegram, какими их проходят с экрана настроек.

    Собирающий обязан держать `_hub`: оттуда берутся мотор и сам вход. Вход
    лежит в хозяйстве, а не здесь, потому что он общий с окном: удавшийся вход
    поднимает бота, а бот рождается и умирает вместе с окном.

    Тела шагов объявлены рядом, а не в этих методах: заслоны и разбор нагрузки
    проверяются своими сторожами, и читать их сквозь три метода поверхности
    значило бы каждый раз поднимать мотор ради двух строк условия.

    Второго написания этих шагов больше нет. Первый запуск ходит сюда же: пока
    поверхностей было две, у мастера стоял свой скелет слота, и слова отказа
    двух написаний разъезжались молча — одна беда числилась в журнале под
    шестью именами.
    """

    def send_code(self, payload: dict) -> dict:
        """Первый шаг: попросить Telegram прислать код на номер.

        Единственный из трёх зовёт вход напрямую, без объявления-заслона рядом.
        Заслонять здесь нечего: два следующих шага стоят в очереди за первым и
        без него бессмысленны, а этот и есть начало — его зовут с любого места.
        """
        try:
            api_id, api_hash, phone = read_credentials(payload)
        except BAD_PAYLOAD as e:
            return bad_fields("send_code", e)

        return reply(
            self._hub.runner,
            step_payload(self._hub.login.send_code(api_id, api_hash, phone)),
        )

    def confirm_code(self, payload: dict) -> dict:
        """Второй шаг: отдать Telegram код из сообщения."""
        try:
            code = read_code(payload)
        except BAD_PAYLOAD as e:
            return bad_fields("confirm_code", e)

        return reply(
            self._hub.runner, step_payload(code_step(self._hub.login, code))
        )

    def confirm_password(self, payload: dict) -> dict:
        """Третий шаг, если Telegram спросил: облачный пароль."""
        try:
            password = read_password(payload)
        except BAD_PAYLOAD as e:
            return bad_fields("confirm_password", e)

        return reply(
            self._hub.runner, step_payload(password_step(self._hub.login, password))
        )
