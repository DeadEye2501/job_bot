"""Файл резюме, на который смотрит окно: выбрать, заменить, открыть."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from client.bridge.answer import _err, _ok
from client.bridge.cv_file import _stat_cv
from client.bridge.payload import _log_invalid_payload


class CvSlots:
    """Резюме как файл, а не как разобранная анкета.

    Слоты окна: выбрать файл, запомнить путь, открыть. Внутрь файла не
    заглядывает никто: разбор резюме моделью отключён, и чтение его текста
    снято вместе с последней дорогой к нему. `cv_file` знает о файле ровно
    то, что говорит о нём файловая система.

    Подмешивающий обязан держать `_rs`, `_parent_widget` и `_dispatch`.
    """

    cv_replace_done = Signal(str)

    @Slot(result=str)
    def pick_cv_file_main(self) -> str:
        """File picker for replacing the CV. Returns the selected file's
        metadata (path + name + size) without saving anything."""
        path, _ = QFileDialog.getOpenFileName(
            self._parent_widget,
            "Выберите файл резюме",
            "",
            "Резюме (*.pdf *.PDF *.md *.MD *.txt *.TXT);;Все файлы (*)",
        )
        if not path:
            return _err("cancelled")
        return _ok({"path": path, **(_stat_cv(path) or {})})

    @Slot(str)
    def replace_cv(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
            path = str(payload.get("path") or "").strip()
        except (ValueError, TypeError) as e:
            _log_invalid_payload("replace_cv", e)
            self.cv_replace_done.emit(_err(f"Неверные поля: {e}"))
            return
        if not path:
            self.cv_replace_done.emit(_err("Путь пустой."))
            return

        async def run() -> str:
            await self._rs.set_app("cv_path", path)
            return _ok({"path": path, **(_stat_cv(path) or {})})

        self._dispatch(self.cv_replace_done, run())

    @Slot()
    def open_cv_file(self) -> None:
        """Open the current CV with the OS-default application."""
        cv_path = self._rs.cv_path
        if not cv_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(cv_path).resolve())))
