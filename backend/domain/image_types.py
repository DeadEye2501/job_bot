"""Тип картинки по её первым байтам — одно правило на вложения Telegram и на окно."""

# WEBP сюда не попадает: у него подпись разорвана — `RIFF`, четыре байта
# длины, и только потом `WEBP`, поэтому она проверяется отдельно.
_IMAGE_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\x00\x00\x01\x00", "image/x-icon"),
    (b"GIF8", "image/gif"),
)


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
