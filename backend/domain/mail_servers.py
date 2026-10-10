"""Справочник почтовых серверов: человеку незачем искать сервер своей почты в справке.

Порты лежат здесь, а не в адаптере отправки: справочник называет ими серверы, а
отправка по ним выбирает шифрование — одно знание на обе стороны.
"""

SSL_PORT = 465
STARTTLS_PORT = 587
_GMAIL = ("smtp.gmail.com", SSL_PORT)
_YANDEX = ("smtp.yandex.ru", SSL_PORT)
_MAIL_RU = ("smtp.mail.ru", SSL_PORT)
_OUTLOOK = ("smtp.office365.com", STARTTLS_PORT)
_KNOWN_SERVERS = {
    "gmail.com": _GMAIL, "googlemail.com": _GMAIL,
    "yandex.ru": _YANDEX, "ya.ru": _YANDEX, "yandex.com": _YANDEX,
    "mail.ru": _MAIL_RU, "inbox.ru": _MAIL_RU, "list.ru": _MAIL_RU, "bk.ru": _MAIL_RU,
    "outlook.com": _OUTLOOK, "hotmail.com": _OUTLOOK, "live.com": _OUTLOOK,
}


def known_server(address: str | None) -> tuple[str, int] | None:
    """Сервер и порт популярной почты по домену адреса; незнакомой — пусто."""
    return _KNOWN_SERVERS.get((address or "").rpartition("@")[2].lower())
