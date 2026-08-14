"""Файл резюме, на который смотрит окно: запомнить путь, открыть."""

from __future__ import annotations

from pathlib import Path

from client.bridge.answer import denied, reply
from client.bridge.cv_file import _stat_cv
from client.bridge.desktop import open_in_system


class Cv:
    """Резюме как файл, а не как разобранная анкета.

    Примесь к `Profile`; собирающий обязан держать `_hub` — оттуда берутся мотор
    и настройки, в которых лежит путь.

    Внутрь файла не заглядывает никто: разбор резюме моделью отключён, и чтение
    его текста снято вместе с последней дорогой к нему. `cv_file` знает о файле
    ровно то, что говорит о нём файловая система.

    Файл мосту не выбирает никто: диалог был Qt'шный и ушёл вместе с каналом.
    Путь называет страница, а спрашивает его у человека диалог самого окна
    (`Window.create_file_dialog` у pywebview) — зовёт его экран анкеты, слайс Б3.
    """

    def replace(self, payload: dict) -> dict:
        """Запомнить новый путь к резюме и рассказать, что по нему лежит."""
        payload = payload if isinstance(payload, dict) else {}
        path = str(payload.get("path") or "").strip()
        if not path:
            return denied("Путь пустой.")

        async def run() -> dict:
            await self._hub.rs.set_app("cv_path", path)
            return {"path": path, **(_stat_cv(path) or {})}

        return reply(self._hub.runner, run())

    def open(self) -> dict:
        """Открыть нынешнее резюме тем, чем его открывает система.

        Ответ пустой, но он есть: у зова, который ничего не вернул, окно не
        отличит «открыли» от «не дошло».
        """
        cv_path = self._hub.rs.cv_path
        if not cv_path:
            return denied("Резюме не выбрано.")
        # Полным путём: настройки помнят его таким, каким назвал человек, а
        # система открывает от своего рабочего каталога — у собранного
        # приложения он чужой.
        if not open_in_system(str(Path(cv_path).resolve())):
            return denied("Не удалось открыть резюме.", path=cv_path)
        return {"ok": {"path": cv_path}}
