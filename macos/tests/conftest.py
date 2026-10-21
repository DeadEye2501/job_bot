"""Стенд тестов мак-двойников: каталог данных — свежий временный.

`config` берёт каталог данных из `APPDATA` на Windows и из домашнего каталога
на маке. Обе подменяются до первого ввоза приложения, чтобы замок, журнал и
база тестов не легли в боевой каталог человека. Общий стенд `tests/conftest.py`
здесь не годится: его сторож каталога смотрит только на `APPDATA`, а на маке
её никто не читает.
"""

import os
import tempfile

_ROOT = tempfile.mkdtemp(prefix="jobbot-mac-tests-")
os.environ["APPDATA"] = _ROOT
os.environ["HOME"] = _ROOT
