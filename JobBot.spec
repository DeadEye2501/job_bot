# PyInstaller spec — single-file Windows .exe for Job Bot.
#
# Запуск:  pipenv run pyinstaller JobBot.spec
#
# Notes:
#   - onefile + windowed: MSVC-style console спрятан, app выглядит как
#     обычное Win-приложение.
#   - datas: подтягиваем client/web (HTML/CSS/JS/шрифты), alembic-окружение
#     (alembic.ini + alembic/{env.py,script.py.mako,versions/*}) и иконку.
#   - hiddenimports: alembic versions модули, async SQLite-драйвер и
#     keyring-бэкенд для Windows — все три загружаются динамически и не
#     попадают в граф импортов PyInstaller'а сами.
#   - pyz onefile-builds для Qt + WebEngine получаются ~250-350 МБ и
#     стартуют 5-15 сек (распаковка во временный _MEIPASS-каталог).

import os

block_cipher = None

datas = [
    ('client/web', 'client/web'),
    ('client/icon.ico', 'client'),
    ('alembic.ini', '.'),
    ('alembic/env.py', 'alembic'),
    ('alembic/script.py.mako', 'alembic'),
    # Включаем ТОЛЬКО init-миграцию. Seed-миграция
    # (aa4e0de05368_seed_initial_data.py) содержит персональные
    # данные разработчика (CV, опыт, скиллы, подписанные каналы) и
    # gitignored — в дистрибутив для других пользователей она
    # попадать НЕ должна. Без неё новый пользователь получает чистую
    # БД, runtime_settings._APP_DEFAULTS и first-run wizard, как и
    # задумано в README/config.py.
    ('alembic/versions/dcdb3ecb3a6f_init.py', 'alembic/versions'),
]

hiddenimports = [
    # Async SQLite driver — подгружается через DSN, граф импортов не видит.
    'aiosqlite',
    # Keyring-бэкенды на Windows: 'win32cred' / WinVaultKeyring подбираются
    # рантайм-сканированием entry_points'ов keyring'а.
    'keyring.backends.Windows',
    'keyring.backends.fail',
    # alembic/env.py и init-миграция загружаются через importlib рантайм
    # (load_python_file), а не статическим импортом из main — PyInstaller
    # не видит их транзитивные импорты в графе. Перечисляем явно всё,
    # что они используют. logging.config — submodule, поэтому даже при
    # уже включённом logging его надо запросить отдельно.
    'logging.config',
    'logging.handlers',
    'alembic.versions.dcdb3ecb3a6f_init',
]


a = Analysis(
    ['main.py'],
    pathex=[os.path.abspath(SPECPATH)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='JobBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX часто ломает Qt-DLL'ки и antivirus орёт
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
