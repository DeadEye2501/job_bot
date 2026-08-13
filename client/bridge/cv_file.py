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
