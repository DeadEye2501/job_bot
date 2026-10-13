"""Инструменты браузера для агента: открыть, снять, нажать, ввести, выбрать, приложить резюме."""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from backend.agent.confirm import is_checked
from backend.agent.jobs import ApplyJob, Dropped
from backend.agent.kit import AgentKit
from backend.agent.page_fields import field_or_none, page_field

logger = logging.getLogger(__name__)

_WAIT_MS = 15_000
_SNAPSHOT_LIMIT = 60_000
_CUT_MARK = "\n… снимок обрезан: страница длиннее, чем помещается в ответ."


class _Refused(Exception):
    """Ввод, которого человек не подтверждал: на страницу он не попадает."""


def browser_tools(kit: AgentKit, resume: Path | None, confirming: ApplyJob | None = None) -> list[Callable]:
    """Инструменты над вкладкой агента. Ответ действия — «готово; адрес: …» или «не вышло: …».

    `confirming` — отклик под подтверждением: ввод, выбор и нажатия делают
    только подтверждённое человеком, а после «Закончить» — ничего.
    """
    act, fill, select, click = _actions(kit, confirming)

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
        """Выбрать значение в выпадающем списке."""
        return await act(lambda page: select(page, selector, value))

    async def browser_attach_resume(selector: str) -> str:
        """Приложить резюме: селектор — кнопка или поле загрузки, видимые в снимке."""
        if resume is None:
            return "нет файла резюме"
        return await act(lambda page: _attach(page, selector, resume))

    async def browser_back() -> str:
        """Вернуться на предыдущую страницу."""
        return await act(lambda page: page.go_back())

    return [browser_open, browser_snapshot, browser_click, browser_type,
            browser_select, browser_attach_resume, browser_back]


def _actions(kit: AgentKit, job: ApplyJob | None) -> tuple[Callable, Callable, Callable, Callable]:
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
        logger.info("ввод агента без подтверждения отклонён: %s", refusal)
        return f"не вышло: {refusal}"
    except PlaywrightError as error:
        logger.info("действие агента в браузере не вышло: %s", _first_line(error))
        return f"не вышло: {_first_line(error)}"
    return f"готово; адрес: {page.url}"


def _plain() -> tuple[Callable, Callable, Callable]:
    """Ввод, выбор и нажатие как есть."""

    def fill(page, selector, text):
        return page.fill(selector, text, timeout=_WAIT_MS)

    def select(page, selector, value):
        return page.select_option(selector, value, timeout=_WAIT_MS)

    def click(page, selector):
        return page.click(selector, timeout=_WAIT_MS)

    return fill, select, click


def _strict(job: ApplyJob) -> tuple[Callable, Callable, Callable]:
    """Ввод, выбор и нажатие под подтверждением человека.

    Текст — только подтверждённый и только в своё поле. Вариант списка выбирает
    агент, ближайший к подтверждённому тексту, но поле должно быть подтверждено.
    Нажатие на подтверждённую галочку ставит подтверждённую отметку, а не
    переключает её: повторное нажатие отметку не снимет. Нажатия не по полям —
    резюме, «Отправить», переходы — как есть.
    """
    plain_fill, plain_select, plain_click = _plain()

    async def fill(page, selector, text):
        item = _confirmed_field(job, page, selector)
        if text != item["value"]:
            raise _Refused(f"вписать можно только подтверждённое: «{item['value']}»")
        await plain_fill(page, selector, text)

    async def select(page, selector, value):
        _confirmed_field(job, page, selector)
        await plain_select(page, selector, value)

    async def click(page, selector):
        item = job.confirmed.get((page.url, selector))
        if item is not None and item["kind"] == "check":
            await page.set_checked(selector, is_checked(item), timeout=_WAIT_MS)
            return
        if item is None:
            await _refuse_unconfirmed_choice(job, page, selector)
        await plain_click(page, selector)

    return fill, select, click


async def _refuse_unconfirmed_choice(job: ApplyJob, page, selector: str) -> None:
    """Нажатие по галочке или кружку, которых человек не подтверждал, — тоже ввод.

    Кружок проходит, если подтверждена его группа: вариант, ближайший к
    подтверждённому тексту, выбирает агент — как в выпадающем списке.
    """
    kind, group, _ = await page_field(page, selector)
    if kind == "check":
        raise _Refused("галочка не подтверждена человеком — сначала need_human с kind=confirm")
    if kind == "radio" and (not group or group not in await _confirmed_groups(job, page)):
        raise _Refused("переключатель не подтверждён человеком — сначала need_human с kind=confirm")


async def _confirmed_groups(job: ApplyJob, page) -> set[str]:
    """Группы кружков, подтверждённых на этой странице пунктом-переключателем.
    Поле прошлого шага формы, ушедшее со страницы, группы не даёт."""
    groups = set()
    for (url, selector), item in job.confirmed.items():
        if url == page.url and item["kind"] == "choice":
            field = await field_or_none(page, selector)
            if field is not None:
                groups.add(field.group)
    return groups


def _going() -> None:
    """Не под подтверждением действия ничто не держит."""


def _not_finished(job: ApplyJob) -> None:
    if isinstance(job.outcome, Dropped):
        raise _Refused("человек закончил работу по этой вакансии — заверши работу")


def _confirmed_field(job: ApplyJob, page, selector: str) -> dict:
    """Пункт, подтверждённый человеком для этого поля на этой странице."""
    item = job.confirmed.get((page.url, selector))
    if item is None:
        raise _Refused("поле не подтверждено человеком на этой странице — сначала need_human с kind=confirm")
    return item


async def _snapshot(kit: AgentKit) -> str:
    from playwright.async_api import Error as PlaywrightError

    page = await kit.browser.page()
    try:
        tree = await page.locator("body").aria_snapshot(timeout=_WAIT_MS)
        title = await page.title()
    except PlaywrightError as error:
        logger.info("снимок страницы не снят: %s", _first_line(error))
        return f"не вышло: {_first_line(error)}"
    seen = f"Адрес: {page.url}\nЗаголовок: {title}\n{tree}"
    return seen if len(seen) <= _SNAPSHOT_LIMIT else seen[:_SNAPSHOT_LIMIT] + _CUT_MARK


async def _attach(page, selector: str, resume: Path) -> None:
    """Поле файла обычно скрыто: нажимается названное и ловится окно выбора файла.
    Окно не открылось — путь кладётся в само поле, если селектор указывает на него."""
    from playwright.async_api import Error as PlaywrightError

    try:
        async with page.expect_file_chooser(timeout=_WAIT_MS) as chooser_info:
            await page.click(selector, timeout=_WAIT_MS)
        chooser = await chooser_info.value
        await chooser.set_files(str(resume))
    except PlaywrightError:
        await page.set_input_files(selector, str(resume), timeout=_WAIT_MS)


def _first_line(error: Exception) -> str:
    return str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
