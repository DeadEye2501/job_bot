"""Текст резюме, вынутый из файла на диске.

Сосед по слою — `telegraph.py`: там внешний источник тоже сводится к тексту,
которым потом кормят модель. Отличает источник — там страница по адресу, здесь
файл, который человек выбрал в окне.
"""

import codecs
import logging
from pathlib import Path
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PyPdfError

logger = logging.getLogger(__name__)


def _pdf_text(path: Path) -> str:
    """Страницы подряд, строки — в том порядке, в каком стоят на листе.

    Порядок просят у читателя нарочно: сам по себе он отдаёт строки в том
    порядке, в каком их записали в файл, а у свёрстанного резюме он другой.
    Заголовки «Достижения», «Обязанности», «Стек» тогда приезжают пустыми
    подряд, а их пункты сваливаются ниже общей кучей, перемешанные между
    работами. Разбирать такой текст бессмысленно любой моделью: связи работы
    с её пунктами в нём уже нет.
    """
    return "\n".join(
        page.extract_text(extraction_mode="layout") for page in PdfReader(path).pages
    )


_PARAGRAPH = qn("w:p")

# Обёртки, внутри которых лежит текст: таблица со своими строками и ячейками и
# «элемент управления содержимым», которым Word заворачивает поля шаблона.
# Каждую надо раскрыть, а не пройти мимо: обход, знающий одни абзацы, потерял
# бы всю таблицу молча.
_WRAPPERS = frozenset(
    {qn("w:tbl"), qn("w:tr"), qn("w:tc"), qn("w:sdt"), qn("w:sdtContent")}
)


def _docx_lines(parent, document: Document) -> list[str]:
    """Строки документа сверху вниз, как они идут в нём самом.

    Порядок между абзацами и таблицами тот же, что в файле: подпись под
    таблицей иначе уехала бы к следующей работе.
    """
    lines = []
    for block in parent.iterchildren():
        if block.tag == _PARAGRAPH:
            lines.append(Paragraph(block, document).text)
        elif block.tag in _WRAPPERS:
            lines.extend(_docx_lines(block, document))
    return lines


def _docx_text(path: Path) -> str:
    document = Document(str(path))
    return "\n".join(_docx_lines(document.element.body, document))


def _plain_text(path: Path) -> str:
    """Кодировку выбирает содержимое, а не уговор.

    Метку порядка байтов в начале ставит «Блокнот», и пробелом она не
    считается: не сними её здесь — она уедет в модель невидимым первым
    символом. Русский текстовый файл с русской Windows приходит в cp1251, и
    целый, читаемый файл падал бы на первой же кириллической букве.
    """
    raw = path.read_bytes()
    # Двухбайтовые метки порядка проверяются первыми и по самим байтам:
    # однобайтовая кодировка разбирает такой файл без всякой ошибки — в
    # бессмыслицу с нулями между буквами, и до неё дело доходить не должно.
    for mark, encoding in ((codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16")):
        if raw.startswith(mark):
            return raw.decode(encoding)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1251")


_READERS = {
    ".pdf": _pdf_text,
    ".docx": _docx_text,
    ".txt": _plain_text,
    ".md": _plain_text,
}

READABLE_SUFFIXES: tuple[str, ...] = tuple(_READERS)
"""Расширения, которые читаются. Перечень один: диалог выбора файла в окне
собирает свой фильтр из него, иначе новый формат пришлось бы вписывать в два
места, а о втором никто бы не напомнил.
"""

# Беды, означающие «расширение обещало не то, что внутри»: переименованный ради
# фильтра диалога `.doc`, книга Excel под именем `.docx`, PDF под паролем, файл
# в кодировке, которую не разобрать. `ValueError` сюда входит целиком: им
# python-docx отвечает на «это не документ Word», и им же кончается неудачное
# раскодирование.
_LIES_ABOUT_FORMAT = (PackageNotFoundError, PyPdfError, BadZipFile, ValueError)


def read_cv_text(path: Path) -> tuple[str | None, str | None]:
    """Текст резюме либо причина, по которой его нет.

    Причины разведены, потому что человеку они говорят разное и чинятся
    по-разному: пропавший файл выбирают заново, `.doc` и запароленный PDF
    пересохраняют, а скан без буквенного слоя не спасёт ни то, ни другое.
    """
    if not path.is_file():
        return None, "no_file"
    reader = _READERS.get(path.suffix.lower())
    if reader is None:
        logger.info("резюме %s: формат %s не читается", path.name, path.suffix)
        return None, "bad_format"
    try:
        text = reader(path).strip()
    except OSError:
        logger.info("резюме %s: файл пропал, пока его читали", path.name)
        return None, "no_file"
    except _LIES_ABOUT_FORMAT as trouble:
        logger.info(
            "резюме %s: внутри не %s (%s)", path.name, path.suffix, trouble
        )
        return None, "bad_format"
    if not text:
        logger.info("резюме %s: в файле не нашлось текста", path.name)
        return None, "no_text"
    return text, None
