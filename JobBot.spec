# PyInstaller spec — single-file Windows .exe for Job Bot.
#
# Запуск:  pipenv run python -m PyInstaller JobBot.spec --clean --noconfirm
#
# Notes:
#   - onefile + windowed: MSVC-style console спрятан, app выглядит как
#     обычное Win-приложение.
#   - datas: подтягиваем собранный фронт (client/web/dist), alembic-окружение
#     (alembic.ini + alembic/{env.py,script.py.mako,versions/*}) и иконку.
#     Собранный, а не исходный: окно раздаёт себе `dist`, а исходники рядом с
#     ним — это ещё и node_modules на сотни мегабайт.
#   - hiddenimports: async SQLite-драйвер, keyring-бэкенд для Windows и пара
#     submodule'ов logging — все подгружаются динамически и в граф импортов
#     PyInstaller'а сами не попадают.
#   - Qt в сборке больше нет: окно рисует pywebview поверх системного
#     WebView2, и от прежних 250-350 МБ с QtWebEngine осталась малая доля.
#   - binaries: библиотеки движка эмбеддингов (llama-cpp) — он грузит их сам
#     из своей папки `lib`, и граф импортов их не видит. Файл модели в exe
#     не вшивается: onefile распаковывал бы сотни мегабайт на каждом старте,
#     путь к модели задаётся в настройках.
#   - SDK Anthropic подтягивается целиком: часть его модулей грузится лениво.
#
# Перед сборкой фронт собирается своим сборщиком:
#     cd client/web && npm run build
# Без этого в exe уедет старый `dist`, а при его отсутствии — ничего.

import os

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

binaries = collect_dynamic_libs('llama_cpp')

datas = [
    ('client/web/dist', 'client/web/dist'),
    ('client/icon.ico', 'client'),
    ('alembic.ini', '.'),
    ('alembic/env.py', 'alembic'),
    ('alembic/script.py.mako', 'alembic'),
    ('alembic/versions/e560edf8b958_init.py', 'alembic/versions'),
]

hiddenimports = [
    # Async SQLite driver — подгружается через DSN, граф импортов не видит.
    'aiosqlite',
    # Keyring-бэкенды на Windows: 'win32cred' / WinVaultKeyring подбираются
    # рантайм-сканированием entry_points'ов keyring'а.
    'keyring.backends.Windows',
    'keyring.backends.fail',
    # alembic/env.py и init-миграция загружаются через importlib рантайм
    # (load_python_file через spec_from_file_location), а не статическим
    # импортом из main — PyInstaller не видит их транзитивные импорты
    # в графе. logging.config — submodule, поэтому даже при уже
    # включённом logging его надо запросить отдельно.
    #
    # NB: саму init-миграцию через hiddenimports перечислять смысла
    # нет — alembic-хеши часто начинаются с цифры (например,
    # e560edf8b958_init), а Python identifier с цифры не начинается,
    # PyInstaller просто молча скипает такие записи. Файл попадает в
    # бандл через datas (см. выше) и alembic находит его при сканировании
    # versions/-каталога по имени файла, не по импорту.
    'logging.config',
    'logging.handlers',
    # Движок эмбеддингов импортируется внутри функции, только когда выбран
    # файл модели, — называем его явно, чтобы он наверняка попал в граф.
    'llama_cpp',
    *collect_submodules('anthropic'),
]


a = Analysis(
    ['main.py'],
    pathex=[os.path.abspath(SPECPATH)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='JobBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX ломает подписи DLL и antivirus орёт
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # GUI-приложение, без консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='client/icon.ico',
)
