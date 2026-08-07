"""Следствия, которые наблюдают тесты `config.py`.

Каталог данных подменён стендом на временный, поэтому тесты видят настоящее
создание папок, а не боевой каталог пользователя. Ветка выбирается по
`sys.platform`: на не-Windows эти тесты не имеют смысла и туда не поедут.
"""

from config import APP_NAME, get_data_dir, get_database_url
from tests.conftest import TMP_ROOT


def test_the_data_dir_is_created_on_first_use(monkeypatch, tmp_path):
    """Каталог данных создаётся на первом обращении."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    expected = tmp_path / APP_NAME
    assert not expected.exists()

    got = get_data_dir()

    assert got == expected
    assert got.is_dir()


def test_asking_again_for_an_existing_dir_does_not_fail(monkeypatch, tmp_path):
    """Повторное обращение к существующему каталогу не падает."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    first = get_data_dir()

    second = get_data_dir()

    assert first == second
    assert second.is_dir()


def test_the_database_url_points_at_a_file_in_the_data_dir():
    """Строка подключения ведёт к файлу в каталоге данных."""
    url = get_database_url()

    assert url.startswith("sqlite+aiosqlite:///")
    assert url.endswith("/jobbot.db")
    assert TMP_ROOT.as_posix() in url


def test_the_database_url_follows_the_data_dir(monkeypatch, tmp_path):
    """Строка подключения переезжает вслед за каталогом."""
    monkeypatch.setenv("APPDATA", str(tmp_path))

    url = get_database_url()

    assert tmp_path.as_posix() in url
