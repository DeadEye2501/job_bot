"""Почта для откликов: пароль лежит шифром, Gmail настраивается сам."""

from backend.log_secrets import SecretRedactionFilter
from backend.models import MailAccount
from backend.repository.mail_account import MailSettings, get_mail_account, save_mail_account
from tests.backend.fixtures.logs import record
from tests.dbio import only_row


async def test_a_saved_account_comes_back_decrypted(session):
    async with session.begin():
        await save_mail_account(session, MailSettings("me@mail.test", "secret", "smtp.mail.test", 587))
    account = await get_mail_account(session)
    assert (account.address, account.host, account.port, account.password) == (
        "me@mail.test", "smtp.mail.test", 587, "secret"
    )


async def test_the_password_is_not_stored_in_the_clear(session, session_factory):
    async with session.begin():
        await save_mail_account(session, MailSettings("me@mail.test", "secret", "smtp.mail.test", 587))
    assert "secret" not in (await only_row(session_factory, MailAccount)).password_encrypted


async def test_gmail_needs_no_server(session):
    async with session.begin():
        await save_mail_account(session, MailSettings("me@gmail.com", "secret", None, None))
    account = await get_mail_account(session)
    assert (account.host, account.port) == ("smtp.gmail.com", 465)


async def test_a_server_without_a_port_goes_by_ssl(session):
    async with session.begin():
        await save_mail_account(session, MailSettings("me@mail.test", "secret", "smtp.mail.test", None))
    assert (await get_mail_account(session)).port == 465


async def test_no_password_means_no_mail(session):
    async with session.begin():
        await save_mail_account(session, MailSettings("me@mail.test", None, "smtp.mail.test", 587))
    assert await get_mail_account(session) is None


async def test_a_blank_password_keeps_the_saved_one(session):
    async with session.begin():
        await save_mail_account(session, MailSettings("me@mail.test", "secret", "smtp.mail.test", 587))
    async with session.begin():
        await save_mail_account(session, MailSettings("me@mail.test", None, "smtp.mail.test", 587))
    assert (await get_mail_account(session)).password == "secret"


async def test_a_saved_password_never_reaches_the_log(session):
    """Пароль не похож ни на один образец, а в журнал попадает в тексте ошибки входа."""
    async with session.begin():
        await save_mail_account(session, MailSettings("me@mail.test", "Kx9-mail", "smtp.mail.test", 465))
    entry = record("535 вход Kx9-mail отклонён")

    SecretRedactionFilter().filter(entry)

    assert "Kx9-mail" not in entry.msg
