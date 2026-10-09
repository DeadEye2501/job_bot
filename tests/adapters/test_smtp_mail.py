"""Письмо уходит по SMTP с вложенным резюме и входом под паролем приложения."""

from adapters.smtp_mail import MailAccountConfig, OutgoingMail, send_mail


class _FakeSmtp:
    sent: list = []
    logins: list = []
    events: list = []

    def __init__(self, host, port, **_options):
        self.where = (host, port)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, **_options):
        _FakeSmtp.events.append(("starttls", self.where))

    def login(self, user, password):
        _FakeSmtp.logins.append((user, password))
        _FakeSmtp.events.append(("login", self.where))

    def send_message(self, message):
        _FakeSmtp.sent.append(message)


def _resume(tmp_path):
    resume = tmp_path / "cv.pdf"
    resume.write_bytes(b"%PDF")
    return resume


def test_a_letter_goes_out_with_the_resume_attached(monkeypatch, tmp_path):
    monkeypatch.setattr(_FakeSmtp, "sent", [])
    monkeypatch.setattr(_FakeSmtp, "logins", [])
    monkeypatch.setattr(_FakeSmtp, "events", [])
    monkeypatch.setattr("smtplib.SMTP_SSL", _FakeSmtp)

    send_mail(
        MailAccountConfig("me@mail.test", "smtp.mail.test", 465, "secret"),
        OutgoingMail("hr@site.test", "Отклик", "Текст", _resume(tmp_path)),
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
        OutgoingMail("hr@site.test", "Отклик", "Текст", _resume(tmp_path)),
    )

    where = ("smtp.mail.test", 587)
    assert _FakeSmtp.events == [("starttls", where), ("login", where)]
    assert len(_FakeSmtp.sent) == 1
