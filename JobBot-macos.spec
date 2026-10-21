# PyInstaller spec — JobBot.app для macOS (Apple Silicon).
#
# Запуск (на маке, из корня репозитория):
#     cd client/web && npm run build
#     bash macos/make_icns.sh
#     PIPENV_PIPFILE=macos/Pipfile pipenv run python -m PyInstaller JobBot-macos.spec --clean --noconfirm
#
# Списки повторяют `JobBot.spec`: общий источник у двух spec потребовал бы
# правки Windows-сборки. Отличия:
#   - onedir + BUNDLE вместо onefile: onefile с окном PyInstaller на маке не
#     поддерживает, а `.app` — это и есть папка.
#   - keyring-бэкенд мака вместо Windows.
#   - мак-двойники названы поимённо: их грузит `importlib.import_module` по
#     строке, чтобы Windows-сборка их не видела, — значит, не видит и эта.
#     Так же по строке pywebview выбирает свой Cocoa-бэкенд.

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

# Номер версии бандла берётся у приложения. Корня репозитория в путях
# сборщика может не быть, поэтому он ставится строкой ниже.
sys.path.insert(0, os.path.abspath(SPECPATH))
from backend.app_version import VERSION

binaries = collect_dynamic_libs('llama_cpp')

datas = [
    ('client/web/dist', 'client/web/dist'),
    # Окно ищет её при каждом старте и пишет предупреждение, не найдя; Cocoa
    # её не показывает — значок Dock берётся из .icns бандла.
    ('client/icon.ico', 'client'),
    ('alembic.ini', '.'),
    ('alembic/env.py', 'alembic'),
    ('alembic/script.py.mako', 'alembic'),
    ('alembic/versions/032b8b1c9f8a_init.py', 'alembic/versions'),
    *collect_data_files('playwright'),
]

hiddenimports = [
    'aiosqlite',
    'keyring.backends.macOS',
    'keyring.backends.fail',
    'logging.config',
    'logging.handlers',
    'llama_cpp',
    *collect_submodules('anthropic'),
    *collect_submodules('mcp', filter=lambda name: not name.startswith('mcp.cli')),
    *collect_submodules('uvicorn'),
    'playwright.async_api',
    'webview.platforms.cocoa',
    'adapters.process_macos',
    'adapters.app_tied_macos',
    'adapters.tie_watch_macos',
    'adapters.browser_macos',
    'adapters.install_places_macos',
    'client.bridge.desktop_macos',
    'client.window_size_macos',
    'client.trouble_macos',
    'backend.updater_macos',
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
    [],
    exclude_binaries=True,
    name='JobBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='JobBot',
)

app = BUNDLE(
    coll,
    name='JobBot.app',
    icon='build/JobBot.icns',
    bundle_identifier='com.deadeye.jobbot',
    info_plist={'CFBundleShortVersionString': VERSION},
)
