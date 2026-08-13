"""Что можно узнать о файле резюме с диска."""

from __future__ import annotations

from pathlib import Path


def _stat_cv(cv_path: str) -> dict | None:
    if not cv_path:
        return None
    try:
        p = Path(cv_path)
        st = p.stat()
        return {"name": p.name, "size": st.st_size, "exists": True}
    except OSError:
        return {"name": Path(cv_path).name, "size": 0, "exists": False}


def _read_cv_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")
