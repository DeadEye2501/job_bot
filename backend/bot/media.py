"""Вложения: распознание, кэш и скачивание."""

import logging
import shutil

from config import get_data_dir
from pathlib import Path


logger = logging.getLogger(__name__)


# Where downloaded media gets cached. Lives next to the SQLite DB under
# the OS user-data dir (``%APPDATA%/JobBot/media`` on Windows) so the .exe
# distribution doesn't end up writing under Program Files.
MEDIA_DIR = get_data_dir() / "media"


PHOTO_EXTS = {".png", ".jpg", ".jpeg", ".webp"}  # GIFs go via send_document → preserved as animation


# WEBP сюда не попадает: у него подпись разорвана — `RIFF`, четыре байта
# длины, и только потом `WEBP`, поэтому она проверяется отдельно.
_IMAGE_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\x00\x00\x01\x00", "image/x-icon"),
    (b"GIF8", "image/gif"),
)

_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
"""Что Telegram принимает в send_photo."""


def image_type(head: bytes) -> str | None:
    """Тип картинки по её первым байтам; None — не узнана.

    Одно объявление на отправку вложений и на показ снимков в окне: обе
    стороны не верят имени и расширению, а читают сами байты, и разойдись
    подписи — одна и та же картинка была бы фото для одной и чужим файлом
    для другой. Хватает первых двенадцати байт.
    """
    for signature, kind in _IMAGE_SIGNATURES:
        if head.startswith(signature):
            return kind
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


# User-facing caps на upload. Telegram regular doc-limit ≈ 2 GB, но без
# прогресс-индикатора и cancel'а файлы такого размера повесят UI; эти
# границы — практический разумный максимум для job-bot use-case (резюме,
# скриншоты, портфолио). Превышение → внятный RuntimeError, ловим в bridge.
PHOTO_SIZE_LIMIT = 10 * 1024 * 1024


DOCUMENT_SIZE_LIMIT = 50 * 1024 * 1024


def _has_photo_content(path: Path) -> bool:
    """Начало файла — подпись JPEG, PNG или WEBP.

    Читается содержимое, а не имя: расширение подделывается, а send_photo на
    подделке падает уже на стороне Telegram, и файл не доходит вовсе.
    """
    try:
        with path.open("rb") as f:
            head = f.read(12)
    except OSError:
        logger.warning("не удалось прочесть начало файла %s", path)
        return False
    return image_type(head) in _PHOTO_TYPES


def looks_like_photo(path: Path) -> bool:
    """Эвристика для выбора send_photo vs send_document. Pyrogram (и сам
    Telegram) принимают в send_photo только JPEG/PNG/WEBP — поэтому
    photo-ветка ЖЁСТКО ограничена этими расширениями. HEIC/HEIF/BMP/TIFF
    и т.п. — тоже изображения, но send_photo на них падает на сервере;
    их (как и GIF) уводим в send_document, чтобы файл хотя бы дошёл.
    Содержимое проверяется вторым: расширения мало, оно врёт."""
    suffix = path.suffix.lower()
    if suffix not in PHOTO_EXTS:
        return False
    return _has_photo_content(path)


def classify_media(msg) -> tuple[str | None, str | None]:
    """Return ``(media_kind, media_name)`` for a Pyrogram DM. We persist only
    photos and documents; everything else (sticker / video / voice / etc.)
    falls back to a text bubble with the placeholder set in ``extract_dm_text``.
    """
    if getattr(msg, "photo", None):
        return "photo", None
    doc = getattr(msg, "document", None)
    if doc is not None:
        return "document", getattr(doc, "file_name", None)
    return None, None


def media_cache_path(hr_id: int, tg_message_id: int, ext: str) -> Path:
    """Deterministic cache path so duplicate-row races (handler vs explicit
    send) collide on the same file rather than producing orphans.
    """
    return MEDIA_DIR / str(hr_id) / f"{tg_message_id}{ext}"


def _cache_ext(as_photo: bool, name: str | None) -> str:
    """Расширение файла в кэше.

    Картинку Telegram отдаёт JPEG независимо от того, чем она была у
    отправителя, поэтому у фото расширение своё, а не исходное. Документ
    без расширения вовсе получает `.bin`: путь в кэше собирается из
    номера сообщения, и без расширения два разных вложения одного HR
    легли бы в один файл.
    """
    if as_photo:
        return ".jpg"
    return Path(name or "").suffix or ".bin"


def cache_sent_file(
    src: Path, hr_id: int, tg_message_id: int, *, as_photo: bool
) -> str | None:
    """Положить отправленный файл в кэш вложений; отдать путь для базы.

    Путь тот же, что написал бы скачиватель входящего, — обработчик,
    догнавший это же сообщение, найдёт готовый файл вместо повторной
    загрузки из Telegram.

    Каталог заводится здесь: разметку пути знает этот модуль, и зовущим
    незачем повторять её задом наперёд. Не вышло — сообщение всё равно
    уходит и сохраняется, только без предпросмотра.
    """
    dest = media_cache_path(hr_id, tg_message_id, _cache_ext(as_photo, src.name))
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return media_path_for_db(dest)
    except Exception:
        logger.exception(
            "media cache copy failed (or its folder could not be made)",
            extra={"hr_id": hr_id, "src": str(src), "dest": str(dest)},
        )
        return None


def media_path_for_db(path) -> str:
    """Convert a media-cache absolute path into a posix string relative to
    ``MEDIA_DIR`` for storage. Falls back to the absolute posix form for any
    path outside MEDIA_DIR (shouldn't happen — every cache write goes
    through ``media_cache_path`` — but kept defensive).
    """
    p = Path(path).resolve()
    try:
        return p.relative_to(MEDIA_DIR.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


async def download_media(client, msg, hr_id: int) -> str | None:
    """Download a photo or document to ``media/{hr_id}/{tg_message_id}{ext}``.
    Returns the project-relative posix path or ``None`` if there's no
    supported media on the message. Skips re-download if the file already
    exists (handler/manual-send race writes the same path either way).
    """
    kind, name = classify_media(msg)
    if kind is None:
        return None
    ext = _cache_ext(kind == "photo", name)
    out = media_cache_path(hr_id, msg.id, ext)
    if out.exists():
        return media_path_for_db(out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        path = await client.download_media(msg, file_name=str(out))
    except Exception:
        logger.exception(
            "media download failed (or its folder could not be made)",
            extra={"hr_id": hr_id, "tg_message_id": msg.id, "kind": kind},
        )
        return None
    if not path:
        return None
    return media_path_for_db(path)
