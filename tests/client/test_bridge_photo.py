"""Фото человека: выбор файлом, копия в каталоге медиа, показ и очистка.

Хранится копия, а не исходный файл: исходный человек волен перенести или
удалить, а показ в окне и загрузка на сайт от этого не зависят.
"""

from backend.bot.media import MEDIA_DIR, stored_media
from client.bridge.media import media_file
from tests.client.conftest import WindowThatPicks


def _photo(tmp_path, name: str = "я.jpg", content: bytes = b"jpeg"):
    source = tmp_path / name
    source.write_bytes(content)
    return source


async def _picked(api, ask, hub, source):
    hub.window = WindowThatPicks([str(source)] if source is not None else None)
    return await ask(api.profile.pick_photo)


async def test_the_path_to_the_photo_cannot_be_set_from_the_page(api):
    """Записать путь к фото страница не может — только диалог самого окна."""
    assert not hasattr(api.profile, "store_photo")


async def test_a_picked_photo_is_copied_into_the_media_folder(api, ask, hub, tmp_path):
    await _picked(api, ask, hub, _photo(tmp_path))

    copy = stored_media(hub.rs.photo_path)
    assert copy is not None and copy.read_bytes() == b"jpeg"
    assert copy.resolve().is_relative_to(MEDIA_DIR.resolve())


async def test_the_photo_lives_on_after_the_source_is_gone(api, ask, hub, tmp_path):
    source = _photo(tmp_path)
    await _picked(api, ask, hub, source)

    source.unlink()

    url = (await ask(api.profile.get))["ok"]["photo_url"]
    assert media_file(url).read_bytes() == b"jpeg"
    assert stored_media(hub.rs.photo_path) is not None


async def test_a_second_photo_replaces_the_first_copy(api, ask, hub, tmp_path):
    await _picked(api, ask, hub, _photo(tmp_path, "первое.png", b"png"))
    first = stored_media(hub.rs.photo_path)

    await _picked(api, ask, hub, _photo(tmp_path, "второе.jpg", b"jpeg"))

    assert stored_media(hub.rs.photo_path).read_bytes() == b"jpeg"
    assert not first.exists()


async def test_clearing_removes_the_path_and_the_copy(api, ask, hub, tmp_path):
    await _picked(api, ask, hub, _photo(tmp_path))
    copy = stored_media(hub.rs.photo_path)

    await ask(api.profile.clear_photo)

    assert hub.rs.photo_path == ""
    assert not copy.exists()
    assert (await ask(api.profile.get))["ok"]["photo_url"] is None


async def test_a_closed_dialog_changes_nothing(api, ask, hub, tmp_path):
    await _picked(api, ask, hub, _photo(tmp_path))
    before = hub.rs.photo_path

    answer = await _picked(api, ask, hub, None)

    assert answer["ok"] == {"cancelled": True}
    assert hub.rs.photo_path == before and stored_media(before) is not None


async def test_without_a_photo_the_profile_shows_none(api, ask):
    assert (await ask(api.profile.get))["ok"]["photo_url"] is None
