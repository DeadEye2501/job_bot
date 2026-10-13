"""Поле страницы глазами браузера: вид, группа кружка и обязательность.

Отличие от `tools_browser`: там инструменты, которыми агент действует, здесь —
вопрос к странице, на который отвечает сам браузер. Его задают и строгие
нажатия, и показ пунктов человеку.
"""

import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)

_WAIT_MS = 15_000

# Опора — то, как элемент понимает сам браузер, а не разметка одного сайта:
# обычные галочка и кружок, самодельные с ролью (нажатым может быть и элемент
# внутри них), и подпись, переключающая привязанное к ней поле. Группа кружка —
# его имя или общий `radiogroup`; у безымянного контейнера — его место среди
# прочих. У галочки обязательность только своя: обязательная группа «отметьте
# хотя бы одно» не делает обязательной каждую галочку в ней.
_FIELD_OF = """el => {
  const FIELD = 'input, select, textarea, [role=checkbox], [role=switch], [role=radio], [role=textbox]';
  const target = (el.matches?.(FIELD) && el)
    || el.closest?.('[role=checkbox], [role=switch], [role=radio]')
    || el.closest?.('label')?.control
    || el;
  const type = (target.type || '').toLowerCase();
  const role = (target.getAttribute?.('role') || '').toLowerCase();
  const own = Boolean(target.required) || target.getAttribute?.('aria-required') === 'true';
  if (type === 'checkbox' || role === 'checkbox' || role === 'switch') return ['check', '', own];
  const isRadio = type === 'radio' || role === 'radio';
  const radio = isRadio ? target : target.querySelector?.('input[type=radio], [role=radio]');
  const box = radio?.closest('[role=radiogroup]');
  const boxes = [...document.querySelectorAll('[role=radiogroup]')];
  const group = !radio ? '' : radio.name || box?.id || (box ? 'radiogroup-' + boxes.indexOf(box) : '');
  const named = radio?.name ? [...document.getElementsByName(radio.name)] : [];
  const required = own
    || target.closest?.('[aria-required=true]') !== null
    || named.some((one) => one.required)
    || Boolean(radio?.required);
  return [isRadio ? 'radio' : '', group, required];
}"""


class PageField(NamedTuple):
    """Элемент страницы: вид (`check`, `radio` или пусто — не поле), группа
    кружка и обязательность."""

    kind: str
    group: str
    required: bool


async def page_field(page, selector: str) -> PageField:
    return PageField(*await page.locator(selector).first.evaluate(_FIELD_OF, timeout=_WAIT_MS))


async def field_or_none(page, selector: str) -> PageField | None:
    """Поле, если оно сейчас на странице; иначе пусто — сразу, без ожидания.

    Подтверждённое на прошлом шаге формы того же адреса со страницы уходит, и
    ждать его срок значило бы платить им за каждое нажатие.
    """
    if not await page.locator(selector).count():
        logger.info("поле %s на странице не найдено", selector)
        return None
    return await page_field(page, selector)
