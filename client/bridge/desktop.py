"""Просьбы окна к рабочему столу: открыть ссылку, положить текст в буфер."""

from __future__ import annotations

from PySide6.QtCore import QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication


class DesktopSlots:
    """Два слота без ответа: всё, что они делают, происходит вне приложения."""

    @Slot(str)
    def open_external_url(self, url: str) -> None:
        """Hand a URL off to the OS-default browser / Telegram client.

        Used by the vacancies UI for "go to source post"
        (vacancy.source_url) and "DM the HR" (https://t.me/{username})
        actions — QWebEngineView swallows ``<a target="_blank">`` clicks
        by default, so the JS side calls this slot instead.
        """
        if not url:
            return
        QDesktopServices.openUrl(QUrl(url))

    @Slot(str)
    def copy_to_clipboard(self, text: str) -> None:
        """Копирование в системный буфер для WebEngine UI (Clipboard API там часто недоступен)."""
        cb = QApplication.clipboard()
        if cb:
            cb.setText(text or "")
