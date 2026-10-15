"""Инструменты браузера для агента: открыть, снять, нажать, ввести, выбрать, приложить резюме и фото."""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import NamedTuple

from backend.agent.confirm import is_checked
from backend.agent.jobs import ApplyJob, Dropped, FillJob
from backend.agent.kit import AgentKit
from backend.agent.page_fields import WAIT_MS, field_or_none, page_field

logger = logging.getLogger(__name__)

_SNAPSHOT_LIMIT = 60_000
_CUT_MARK = "\n… снимок обрезан: страница длиннее, чем помещается в ответ."


class _Refused(Exception):
    """Ввод, которого не принимали: на страницу он не попадает."""


class _Ledger(NamedTuple):
    """Принятое для строгого ввода: пункты по ключу «адрес, селектор», чем они
    приняты и каким инструментом агенту их принять."""

    items: dict[tuple[str, str], dict]
    accepted_by: str
    first: str


def _ledger(job: ApplyJob | FillJob) -> _Ledger:
    """Отклик под подтверждением держит подтверждённое человеком, заполнение
    резюме — принятое в раскладке страницы. Решается здесь, один раз."""
    if isinstance(job, ApplyJob):
        return _Ledger(job.confirmed, "подтверждено человеком", "need_human с kind=confirm")
    return _Ledger(job.accepted, "принято в раскладке", "submit_layout")


def browser_tools(
    kit: AgentKit, resume: Path | None, photo: Path | None, strict: ApplyJob | FillJob | None = None
) -> list[Callable]:
    """Инструменты над вкладкой агента. Ответ действия — «готово; адрес: …» или «не вышло: …».

    `strict` — ввод, выбор и нажатия делают только принятое: отклик под
    подтверждением (после «Закончить» — ничего) или заполнение резюме.
    """
    act, fill, select, click = _actions(kit, strict)

    async def browser_open(url: str) -> str:
        """Открыть адрес во вкладке."""
        return await act(lambda page: page.goto(url))

    async def browser_snapshot() -> str:
        """Что сейчас на странице: адрес, заголовок и дерево доступности с адресами ссылок."""
        return await _snapshot(kit)

    async def browser_click(selector: str) -> str:
        """Нажать на элемент по селектору Playwright."""
        return await act(lambda page: click(page, selector))

    async def browser_type(selector: str, text: str) -> str:
        """Ввести текст в поле, заменив прежний."""
        return await act(lambda page: fill(page, selector, text))

    async def browser_select(selector: str, value: str) -> str:
        """Выбрать значение в родном списке (select). Самодельный список — browser_click по полю, затем по варианту."""
        return await act(lambda page: select(page, selector, value))

    async def browser_back() -> str:
        """Вернуться на предыдущую страницу."""
        return await act(lambda page: page.go_back())

    return [browser_open, browser_snapshot, browser_click, browser_type,
            browser_select, *_attach_tools(act, resume, photo, strict), browser_back]


def _attach_tools(act: Callable, resume: Path | None, photo: Path | None,
                  job: ApplyJob | FillJob | None) -> list[Callable]:
    """Приложить резюме и фото: нет файла — ответ агенту, и на странице ничего не нажато.
    Вложение меняет резюме так же, как ввод, и при заполнении проходит ту же
    проверку, что раскладка: на странице не того резюме файл не прикладывается."""

    async def attach(page, selector: str, file: Path) -> None:
        if isinstance(job, FillJob) and job.off_target(page.url):
            raise _Refused("это страница другого резюме")
        await _attach(page, selector, file)

    async def browser_attach_resume(selector: str) -> str:
        """Приложить резюме: селектор — кнопка или поле загрузки, видимые в снимке."""
        if resume is None:
            return "нет файла резюме"
        return await act(lambda page: attach(page, selector, resume))

    async def browser_attach_photo(selector: str) -> str:
        """Приложить фото человека: селектор — кнопка или поле загрузки, видимые в снимке."""
        if photo is None:
            return "нет фото"
        return await act(lambda page: attach(page, selector, photo))

    return [browser_attach_resume, browser_attach_photo]


def _actions(kit: AgentKit, job: ApplyJob | FillJob | None) -> tuple[Callable, Callable, Callable, Callable]:
    """Действие над страницей и ввод, выбор, нажатие — обычные или под подтверждением.

    После «Закончить» не проходит ни одно действие — решается здесь, один раз на
    все инструменты: и «Отправить», и нажатие при загрузке резюме.
    """
    fill, select, click = _plain() if job is None else _strict(job)
    held = _going if job is None else lambda: _not_finished(job)

    async def act(action: Callable[..., Awaitable]) -> str:
        return await _act(kit, action, held)

    return act, fill, select, click


async def _act(kit: AgentKit, action: Callable[..., Awaitable], held: Callable[[], None]) -> str:
    """Действие над страницей. Отказ Playwright — исход для агента, а не беда приложения:
    агент получает текст и решает сам."""
    from playwright.async_api import Error as PlaywrightError

    page = await kit.browser.page()
    try:
        held()
        await action(page)
    except _Refused as refusal:
        logger.info("ввод агента вне принятого отклонён: %s", refusal)
        return f"не вышло: {refusal}"
    except PlaywrightError as error:
        logger.info("действие агента в браузере не вышло: %s", _first_line(error))
        return f"не вышло: {_first_line(error)}"
    return f"готово; адрес: {page.url}"


def _plain() -> tuple[Callable, Callable, Callable]:
    """Ввод, выбор и нажатие как есть."""

    def fill(page, selector, text):
        return page.fill(selector, text, timeout=WAIT_MS)

    def select(page, selector, value):
        return page.select_option(selector, value, timeout=WAIT_MS)

    def click(page, selector):
        return page.click(selector, timeout=WAIT_MS)

    return fill, select, click


def _strict(job: ApplyJob | FillJob) -> tuple[Callable, Callable, Callable]:
    """Ввод, выбор и нажатие только принятого: подтверждённого человеком или
    принятого в раскладке (`_ledger`).

    Текст — только принятый и только в своё поле. Вариант списка выбирает
    агент, ближайший к принятому тексту, но поле должно быть принято.
    Нажатие на принятую галочку ставит принятую отметку, а не переключает её:
    повторное нажатие отметку не снимет. Нажатия не по полям — резюме,
    «Отправить», переходы — как есть.
    """
    plain_fill, plain_select, plain_click = _plain()
    ledger = _ledger(job)

    async def fill(page, selector, text):
        item = _accepted_field(ledger, page, selector)
        if text != item["value"]:
            raise _Refused(f"вписать можно только то, что {ledger.accepted_by}: «{item['value']}»")
        await plain_fill(page, selector, text)

    async def select(page, selector, value):
        _accepted_field(ledger, page, selector)
        await plain_select(page, selector, value)

    async def click(page, selector):
        item = ledger.items.get((page.url, selector))
        if item is not None and item["kind"] == "check":
            await page.set_checked(selector, is_checked(item), timeout=WAIT_MS)
            return
        if item is None:
            await _refuse_unaccepted_choice(ledger, page, selector)
        await plain_click(page, selector)

    return fill, select, click


async def _refuse_unaccepted_choice(ledger: _Ledger, page, selector: str) -> None:
    """Нажатие по непринятой галочке или кружку — тоже ввод.

    Кружок проходит, если принята его группа: вариант, ближайший к принятому
    тексту, выбирает агент — как в выпадающем списке.
    """
    kind, group, _ = await page_field(page, selector)
    if kind == "check":
        raise _Refused(f"галочка не {ledger.accepted_by} — сначала {ledger.first}")
    if kind == "radio" and (not group or group not in await _accepted_groups(ledger, page)):
        raise _Refused(f"переключатель не {ledger.accepted_by} — сначала {ledger.first}")


async def _accepted_groups(ledger: _Ledger, page) -> set[str]:
    """Группы кружков, принятых на этой странице пунктом-переключателем.
    Поле прошлого шага формы, ушедшее со страницы, группы не даёт."""
    groups = set()
    for (url, selector), item in ledger.items.items():
        if url == page.url and item["kind"] == "choice":
            field = await field_or_none(page, selector)
            if field is not None:
                groups.add(field.group)
    return groups


def _going() -> None:
    """Не под подтверждением действия ничто не держит."""


def _not_finished(job: ApplyJob | FillJob) -> None:
    if isinstance(job.outcome, Dropped):
        raise _Refused("человек закончил работу по этой вакансии — заверши работу")


def _accepted_field(ledger: _Ledger, page, selector: str) -> dict:
    """Пункт, принятый для этого поля на этой странице."""
    item = ledger.items.get((page.url, selector))
    if item is None:
        raise _Refused(f"поле не {ledger.accepted_by} на этой странице — сначала {ledger.first}")
    return item


async def _snapshot(kit: AgentKit) -> str:
    from playwright.async_api import Error as PlaywrightError

    page = await kit.browser.page()
    try:
        tree = await page.locator("body").aria_snapshot(timeout=WAIT_MS)
        title = await page.title()
    except PlaywrightError as error:
        logger.info("снимок страницы не снят: %s", _first_line(error))
        return f"не вышло: {_first_line(error)}"
    seen = f"Адрес: {page.url}\nЗаголовок: {title}\n{tree}"
    return seen if len(seen) <= _SNAPSHOT_LIMIT else seen[:_SNAPSHOT_LIMIT] + _CUT_MARK


async def _attach(page, selector: str, file: Path) -> None:
    """Поле файла обычно скрыто: нажимается названное и ловится окно выбора файла.
    Окно не открылось — путь кладётся в само поле, если селектор указывает на него."""
    from playwright.async_api import Error as PlaywrightError

    try:
        async with page.expect_file_chooser(timeout=WAIT_MS) as chooser_info:
            await page.click(selector, timeout=WAIT_MS)
        chooser = await chooser_info.value
        await chooser.set_files(str(file))
    except PlaywrightError:
        await page.set_input_files(selector, str(file), timeout=WAIT_MS)


def _first_line(error: Exception) -> str:
    return str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
