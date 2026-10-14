"""Файл резюме, на который смотрит окно: запомнить путь, открыть, разобрать."""

from __future__ import annotations

from contextlib import aclosing
from pathlib import Path

from adapters import lm_studio
from adapters.cv_text import READABLE_SUFFIXES, read_cv_text
from backend.provider_config import LlmProviderConfig
from backend.llm import cv as llm_cv
from backend.repository.app_settings import CV_PATH_KEY
from backend.repository.profile_cv import save_parsed_cv

from client.bridge.answer import denied, launched, reply
from client.bridge.cv_file import _stat_cv
from client.bridge.desktop import chosen_path, closed_dialog, file_filter, open_in_system
from client.bridge.refusals import PARSE_CV_REFUSALS


# Старый двоичный `.doc` дописан к читаемым: разбор его не читает, а приложить
# к отклику можно и его — там нужен только путь.
_RESUME_FILTER = file_filter("Резюме", (*READABLE_SUFFIXES, ".doc"))


class Cv:
    """Резюме как файл, а не как разобранная анкета.

    Примесь к `Profile`; собирающий обязан держать `_hub` — оттуда берутся мотор
    и настройки, в которых лежит путь.

    Внутрь файла отсюда не заглядывают: `cv_file` знает о нём ровно то, что
    говорит файловая система. Текст из него читает `adapters/cv_text`, и зовут
    того из разбора резюме, а не из окна.

    Файл мосту не выбирает никто: диалог был Qt'шный и ушёл вместе с каналом.
    Путь называет страница, а спрашивает его у человека диалог самого окна
    (`Window.create_file_dialog` у pywebview) — зовёт его экран анкеты, слайс Б3.
    """

    def pick(self) -> dict:
        """Спросить у человека файл резюме диалогом самого окна.

        Диалог у окна, а не у моста, и со страницы до него не дотянуться:
        браузер отдаёт выбранный файл содержимым, а не путём, — нарочно, — а
        отклику нужен именно путь, чтобы приложить файл с диска.

        Закрытый диалог отказом не считается: ничего не сломалось, человек
        передумал. Отзовись мост отказом, окно показало бы плашку беды на
        обычном «нет, не сейчас», а пустой путь стёр бы прежнее резюме, и
        следующий отклик ушёл бы без вложения.
        """
        path = chosen_path(self._hub.window, _RESUME_FILTER)
        if path is None:
            return closed_dialog()
        return self._replace({"path": path})

    def _replace(self, payload: dict) -> dict:
        """Запомнить новый путь к резюме и рассказать, что по нему лежит.

        Закрыт от страницы тем же способом, что и отправка файла собеседнику
        (`hr_chat._send_media`): поверхность моста pywebview собирает обходом
        полей и имена с подчёркиванием пропускает. Открытым его звал бы кто
        угодно с любым путём, а записанный путь потом исполняется — «открыть
        резюме» отдаёт его системе без разбора расширения.

        Единственный зовущий — `pick` рядом: путь сюда приходит из диалога
        самого окна, то есть от человека.
        """
        payload = payload if isinstance(payload, dict) else {}
        path = str(payload.get("path") or "").strip()
        if not path:
            return denied("Путь пустой")

        async def run() -> dict:
            await self._hub.rs.set_app(CV_PATH_KEY, path)
            return {"path": path, **(_stat_cv(path) or {})}

        return reply(self._hub.runner, run())

    def parse_cv(self) -> dict:
        """Разобрать записанное резюме моделью и заполнить им анкету.

        Отвечает «пущено», а не исходом: разбор четырёх страниц на местной
        модели идёт больше минуты, и державший бы его зов держал бы и окно.
        Чем кончилось, страница узнаёт вестью — как у обхода каналов и
        отправки отклика.

        Оба заслона стоят до пуска, а не внутри работы: пущенная, она
        вернулась бы вестью через минуту, и всю минуту человек ждал бы того,
        чего не будет.
        """
        cv_path = self._hub.rs.cv_path
        if not cv_path:
            return denied("Резюме не выбрано")
        chat = self._hub.rs.chat
        if chat is None:
            return denied("Модель не выбрана — вернитесь на шаг выбора модели")
        return launched(
            self._hub,
            lambda: _parse_into_profile(self._hub, Path(cv_path), chat),
            PARSE_CV_REFUSALS,
            "Резюме разобрано, анкета заполнена",
        )

    def open(self) -> dict:
        """Открыть нынешнее резюме тем, чем его открывает система.

        Ответ пустой, но он есть: у зова, который ничего не вернул, окно не
        отличит «открыли» от «не дошло».
        """
        cv_path = self._hub.rs.cv_path
        if not cv_path:
            return denied("Резюме не выбрано")
        # Полным путём: настройки помнят его таким, каким назвал человек, а
        # система открывает от своего рабочего каталога — у собранного
        # приложения он чужой.
        if not open_in_system(str(Path(cv_path).resolve())):
            return denied("Не удалось открыть резюме", path=cv_path)
        return {"ok": {"path": cv_path}}


async def _parse_into_profile(hub, path: Path, chat: LlmProviderConfig) -> str:
    """Дорога от файла на диске до заполненной анкеты; отвечает кодом исхода.

    Коды чтения файла уезжают наверх как есть: `read_cv_text` уже развёл
    пропажу, нечитаемый формат и скан без буквенного слоя, и переводить их
    здесь во что-то своё значило бы завести второе место, знающее эти три
    случая.

    Анкета заменяется целиком, вместе с путём к файлу, одной сделкой: разбор
    без записанного источника оставил бы человека с чужой на вид анкетой и без
    следа, откуда она взялась.
    """
    text, trouble = read_cv_text(path)
    if trouble is not None:
        return trouble

    async with aclosing(lm_studio.make_client(chat)) as client:
        parsed = await llm_cv.parse_cv(text, client, chat.model)
    if parsed is None:
        return "unparsed"

    async with hub.session_factory() as session:
        async with session.begin():
            await save_parsed_cv(session, parsed, cv_path=str(path))
    return "ok"
