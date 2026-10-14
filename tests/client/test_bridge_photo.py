"""Фото человека: выбор файлом, обрезка в окне, копия в каталоге медиа, очистка.

Выбранный файл мост отдаёт окну картинкой, окно вырезает нужную часть и
присылает её обратно; хранится копия, а не исходный файл: исходный человек
волен перенести или удалить.
"""

import base64
import os

from backend.bot.media import MEDIA_DIR, stored_media
from client.bridge.media import media_file
from tests.client.conftest import WindowThatPicks
from tests.factories import photo_head

JPEG = photo_head(".jpg") + b"jpeg"
PNG = photo_head(".png") + b"png"


def _data_url(blob: bytes, kind: str = "image/jpeg") -> str:
    return f"data:{kind};base64," + base64.b64encode(blob).decode("ascii")


async def _stored(api, ask, blob: bytes = JPEG):
    return await ask(api.profile.store_photo, _data_url(blob))


async def test_a_picked_photo_comes_back_to_the_window_as_an_image(api, ask, hub, tmp_path):
    """Окну нужна сама картинка: рамку обрезки оно рисует поверх неё."""
    source = tmp_path / "я.jpg"
    source.write_bytes(JPEG)
    hub.window = WindowThatPicks([str(source)])

    answer = await ask(api.profile.pick_photo)

    head, body = answer["ok"]["image"].split(",", 1)
    assert head == "data:image/jpeg;base64" and base64.b64decode(body) == JPEG
    assert hub.rs.photo_path == ""


async def test_a_closed_dialog_changes_nothing(api, ask, hub):
    await _stored(api, ask)
    before = hub.rs.photo_path
    hub.window = WindowThatPicks(None)

    answer = await ask(api.profile.pick_photo)

    assert answer["ok"] == {"cancelled": True}
    assert hub.rs.photo_path == before and stored_media(before) is not None


async def test_a_cropped_photo_is_kept_as_a_copy_in_the_media_folder(api, ask, hub):
    await _stored(api, ask)

    copy = stored_media(hub.rs.photo_path)
    assert copy is not None and copy.read_bytes() == JPEG
    assert copy.resolve().is_relative_to(MEDIA_DIR.resolve())
    url = (await ask(api.profile.get))["ok"]["photo_url"]
    assert media_file(url.split("?")[0]).read_bytes() == JPEG


async def test_what_is_not_an_image_is_refused_and_nothing_changes(api, ask, hub):
    """Картинку присылает страница, и путь вместо неё ничего не записывает."""
    await _stored(api, ask)
    before = hub.rs.photo_path

    for sent in ("C:/Windows/notepad.exe", _data_url(b"MZ\x90\x00", "image/jpeg")):
        answer = await ask(api.profile.store_photo, sent)
        assert "fail" in answer

    assert hub.rs.photo_path == before and stored_media(before).read_bytes() == JPEG


async def test_a_new_photo_replaces_the_old_copy_and_gets_a_new_address(api, ask, hub):
    """Окно держит снимок по адресу: тот же адрес после замены показал бы старое фото."""
    await _stored(api, ask, PNG)
    first = stored_media(hub.rs.photo_path)
    before = (await ask(api.profile.get))["ok"]["photo_url"]

    await _stored(api, ask, JPEG)
    copy = stored_media(hub.rs.photo_path)
    stamp = copy.stat().st_mtime_ns
    os.utime(copy, ns=(stamp + 1_000_000_000, stamp + 1_000_000_000))

    assert copy.read_bytes() == JPEG and not first.exists()
    assert (await ask(api.profile.get))["ok"]["photo_url"] != before


async def test_clearing_removes_the_path_and_the_copy(api, ask, hub):
    await _stored(api, ask)
    copy = stored_media(hub.rs.photo_path)

    await ask(api.profile.clear_photo)

    assert hub.rs.photo_path == ""
    assert not copy.exists()
    assert (await ask(api.profile.get))["ok"]["photo_url"] is None


async def test_a_copy_removed_by_hand_gets_no_address(api, ask, hub):
    await _stored(api, ask)

    stored_media(hub.rs.photo_path).unlink()

    assert (await ask(api.profile.get))["ok"]["photo_url"] is None


async def test_without_a_photo_the_profile_shows_none(api, ask):
    assert (await ask(api.profile.get))["ok"]["photo_url"] is None
