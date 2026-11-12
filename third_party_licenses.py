"""Тексты лицензий всего чужого, что сборка кладёт в приложение.

Почти все эти лицензии требуют прикладывать свой текст к каждой копии
программы, поэтому обе spec собирают файл перед упаковкой и кладут его в бандл.
"""

import json
import os
import re
from importlib.metadata import distribution
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

# Тексты, которых нет в колёсах: proxy-tools и pyobjc-core выходят без файла
# лицензии, а llama.cpp вшит в колесо llama-cpp-python под лицензией только
# самой обёртки. Имя файла — имя пакета в замке.
_SUPPLIED = _ROOT / 'licenses'

# Что сборщик фронта вшивает в `client/web/dist`. Перечень снят по карте
# исходников сборки (`vite build --sourcemap`): сама сборка его не сообщает,
# и новый ввоз из node_modules надо дописать сюда руками.
_FRONT = ('svelte', 'clsx', 'material-symbols')

_LICENSE_FILE = re.compile(r'^(LICEN[CS]E|COPYING|NOTICE)', re.IGNORECASE)


def write_notices(lock: str, out: str) -> str:
    """Собрать лицензии пакетов из `default` замка, Python, llama.cpp и фронта в `out`."""
    sections = [('Python', _python_license())]
    for name in sorted(json.loads(Path(lock).read_text(encoding='utf-8'))['default']):
        sections.append((name, _package_license(name)))
    sections.append(('llama.cpp', (_SUPPLIED / 'llama.cpp.txt').read_text(encoding='utf-8')))
    for name in _FRONT:
        sections.append((name, _front_license(name)))
    text = '\n\n'.join(f'{"=" * 79}\n{name}\n{"=" * 79}\n\n{body.strip()}' for name, body in sections)
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + '\n', encoding='utf-8')
    return out


def _python_license() -> str:
    # Там же ищет его встроенный `license()`: у Windows-сборки Python файл в
    # корне установки, у собранной из исходников — в каталоге стандартной
    # библиотеки.
    lib = Path(os.__file__).parent
    for folder in (lib, lib.parent):
        found = folder / 'LICENSE.txt'
        if found.is_file():
            return found.read_text(encoding='utf-8')
    raise FileNotFoundError(f'LICENSE.txt Python не найден ни в {lib}, ни в {lib.parent}')


def _package_license(name: str) -> str:
    dist = distribution(name)
    files = [f for f in dist.files if '.dist-info' in str(f) and _LICENSE_FILE.match(f.name)]
    if not files:
        return (_SUPPLIED / f'{name}.txt').read_text(encoding='utf-8')
    return '\n\n'.join(f'--- {f.name} ---\n\n{f.read_text(encoding="utf-8")}' for f in files)


def _front_license(name: str) -> str:
    folder = _ROOT / 'client/web/node_modules' / name
    files = sorted(f for f in folder.iterdir() if _LICENSE_FILE.match(f.name))
    if not files:
        raise FileNotFoundError(f'В {folder} нет файла лицензии')
    return '\n\n'.join(f.read_text(encoding='utf-8') for f in files)
