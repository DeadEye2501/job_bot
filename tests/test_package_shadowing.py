"""Сторож сборки: чужой каталог в `sys.path` не подменяет модули проекта.

Пакет без `__init__.py` — пакет-пространство имён, и путь свой он пересчитывает
из `sys.path` при каждом обращении. В собранном exe это оборачивается подменой:
`alembic.ini` просит положить текущий каталог в `sys.path`, и приложение,
запущенное из папки с исходниками, дальше берёт модули оттуда, а не из бандла.
Половина модулей при этом остаётся из сборки — та, что успела загрузиться
раньше, — и разъехавшиеся половины падают на импорте имени, которого в старшей
ещё нет.

Проверяется здесь следствие, а не наличие файла: подложенный каталог не пролезает
внутрь пакета.
"""

import importlib

import pytest


@pytest.mark.parametrize("package", ["backend", "adapters", "client"])
def test_decoy_directory_in_sys_path_does_not_enter_the_package(
    package: str, tmp_path, monkeypatch
) -> None:
    """Модуль из подложенного каталога-двойника пакету не достаётся."""
    decoy = tmp_path / package
    decoy.mkdir()
    (decoy / "decoy.py").write_text("SMUGGLED = True\n", encoding="utf-8")
    monkeypatch.syspath_prepend(tmp_path)
    importlib.invalidate_caches()

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"{package}.decoy")
