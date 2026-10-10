"""Письмо уходит по SMTP с вложенным резюме и входом под паролем приложения."""

import smtplib

from adapters.smtp_mail import MailAccountConfig, OutgoingMail, send_mail
from tests.factories import resume_file


class _FakeSmtp:
    sent: list = []
    logins: list = []
    events: list = []

    def __init__(self, host, port, **_options):
        self.where = (host, port)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        # Как у `smtplib.SMTP`: выход из `with` прощается с сервером.
        self.quit()
        return False

    def quit(self):
        _FakeSmtp.events.append(("quit", self.where))

    def close(self):
        _FakeSmtp.events.append(("close", self.where))

    def starttls(self, **_options):
        _FakeSmtp.events.append(("starttls", self.where))

    def login(self, user, password):
        _FakeSmtp.logins.append((user, password))
        _FakeSmtp.events.append(("login", self.where))

    def send_message(self, message):
        _FakeSmtp.sent.append(message)


def test_a_letter_goes_out_with_the_resume_attached(monkeypatch, tmp_path):
    monkeypatch.setattr(_FakeSmtp, "sent", [])
    monkeypatch.setattr(_FakeSmtp, "logins", [])
    monkeypatch.setattr(_FakeSmtp, "events", [])
    monkeypatch.setattr("smtplib.SMTP_SSL", _FakeSmtp)

    send_mail(
        MailAccountConfig("me@mail.test", "smtp.mail.test", 465, "secret"),
        OutgoingMail("hr@site.test", "Отклик", "Текст", resume_file(tmp_path, "cv.pdf")),
    )

    (message,) = _FakeSmtp.sent
    assert (message["From"], message["To"], message["Subject"]) == (
        "me@mail.test", "hr@site.test", "Отклик"
    )
    assert message.get_body().get_content().strip() == "Текст"
    assert [part.get_filename() for part in message.iter_attachments()] == ["cv.pdf"]
    assert _FakeSmtp.logins == [("me@mail.test", "secret")]


def test_port_587_secures_the_line_before_the_login(monkeypatch, tmp_path):
    """На 587 сервер ждёт STARTTLS, а не шифрования с порога: `SMTP_SSL` там не подключится."""
    monkeypatch.setattr(_FakeSmtp, "sent", [])
    monkeypatch.setattr(_FakeSmtp, "logins", [])
    monkeypatch.setattr(_FakeSmtp, "events", [])
    monkeypatch.setattr("smtplib.SMTP", _FakeSmtp)

    send_mail(
        MailAccountConfig("me@mail.test", "smtp.mail.test", 587, "secret"),
        OutgoingMail("hr@site.test", "Отклик", "Текст", resume_file(tmp_path, "cv.pdf")),
    )

    where = ("smtp.mail.test", 587)
    assert _FakeSmtp.events == [("starttls", where), ("login", where), ("quit", where)]
    assert len(_FakeSmtp.sent) == 1


class _RudeSmtp(_FakeSmtp):
    """Сервер принял письмо, а на прощание ответил не 221."""

    def quit(self):
        raise smtplib.SMTPResponseException(250, b"bye")


def test_a_rude_goodbye_after_an_accepted_letter_is_not_a_failure(monkeypatch, tmp_path):
    """Письмо уже принято: сочти прощание отказом — следующий способ отправил бы второй отклик."""
    monkeypatch.setattr(_FakeSmtp, "sent", [])
    monkeypatch.setattr(_FakeSmtp, "logins", [])
    monkeypatch.setattr(_FakeSmtp, "events", [])
    monkeypatch.setattr("smtplib.SMTP_SSL", _RudeSmtp)

    send_mail(
        MailAccountConfig("me@mail.test", "smtp.mail.test", 465, "secret"),
        OutgoingMail("hr@site.test", "Отклик", "Текст", resume_file(tmp_path, "cv.pdf")),
    )

    assert len(_FakeSmtp.sent) == 1
