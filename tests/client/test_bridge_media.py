"""Снимок, вшитый в ответ окну: тип в адресе — тот, что у самих байтов."""

import pytest

from client.bridge.media import _avatar_data_url


@pytest.mark.parametrize(
    ("head", "kind"),
    [
        pytest.param(b"\x89PNG\r\n\x1a\n", "image/png", id="png"),
        pytest.param(b"\x00\x00\x01\x00\x01\x00", "image/x-icon", id="ico"),
        pytest.param(b"GIF89a", "image/gif", id="gif"),
        pytest.param(b"RIFF\x10\x00\x00\x00WEBPVP8 ", "image/webp", id="webp"),
        pytest.param(b"\xff\xd8\xff\xe0", "image/jpeg", id="jpeg"),
    ],
)
def test_the_data_url_names_the_type_of_its_bytes(head, kind):
    """Значок сайта бывает png, ico, webp, а снимок Telegram — jpeg; назови адрес
    чужой тип, и строгий к нему разбор показал бы пустоту вместо значка."""
    assert _avatar_data_url(head + b"\x00" * 16).startswith(f"data:{kind};base64,")
