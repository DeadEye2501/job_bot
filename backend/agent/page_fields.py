"""Поля страницы глазами браузера.

Два вопроса к странице на общих правилах: одно поле по селектору (вид, группа
кружка, обязательность) и опись всех полей формы.

Отличие от `tools_browser`: там инструменты, которыми агент действует, здесь —
вопрос к странице, на который отвечает сам браузер. Его задают строгие
нажатия, показ пунктов человеку и раскладка страницы при заполнении резюме.
"""

import logging
from typing import NamedTuple

from backend.payloads import FieldEntry

logger = logging.getLogger(__name__)

# Сколько ждать элемент страницы: опрос поля и действия агента на странице
# ждут одинаково, иначе одно и то же поле одно находит, а другое нет. Агент
# действует по свежему снимку: элемента нет за секунду — его нет вовсе.
WAIT_MS = 1_000
# Действия, которым нужно время и при найденном элементе: набор длинного
# текста по клавише, снимок большой страницы, открытие окна выбора файла.
LONG_WAIT_MS = 5_000

# Правила, общие для вопроса об одном поле и для описи страницы: что считать
# полем, какого оно вида, обязательно ли и к какой группе кружков относится.
# Опора — то, как элемент понимает сам браузер, а не разметка одного сайта.
# Группа кружка — его имя или общий `radiogroup`; у безымянного контейнера —
# его место среди прочих. У галочки обязательность только своя: обязательная
# группа «отметьте хотя бы одно» не делает обязательной каждую галочку в ней.
_RULES = r"""
  const FIELD = 'input, select, textarea, [role=checkbox], [role=switch], [role=radio], [role=combobox], [role=textbox]';
  const RADIOS = 'input[type=radio], [role=radio]';
  const kindOf = (el) => {
    const type = (el.type || '').toLowerCase();
    const role = (el.getAttribute?.('role') || '').toLowerCase();
    if (el.localName === 'textarea') return 'textarea';
    if (el.localName === 'select' || role === 'combobox') return 'select';
    if (type === 'checkbox' || role === 'checkbox' || role === 'switch') return 'check';
    if (type === 'radio' || role === 'radio') return 'radio';
    return 'text';
  };
  const ownRequired = (el) => Boolean(el.required) || el.getAttribute?.('aria-required') === 'true';
  const requiredOf = (el) => ownRequired(el)
    || (kindOf(el) !== 'check' && el.closest?.('[aria-required=true]') !== null)
    || (kindOf(el) === 'radio' && Boolean(el.name)
      && [...document.getElementsByName(el.name)].some((one) => one.required));
  const groupOf = (radio) => {
    const box = radio.closest('[role=radiogroup]');
    const boxes = [...document.querySelectorAll('[role=radiogroup]')];
    return radio.name || box?.id || (box ? 'radiogroup-' + boxes.indexOf(box) : '');
  };
"""

# Нажатым может быть и элемент внутри самодельного поля, и подпись,
# переключающая привязанное к ней поле: ответ — о самом поле.
_FIELD_OF = "el => {" + _RULES + """
  const target = (el.matches?.(FIELD) && el)
    || el.closest?.('[role=checkbox], [role=switch], [role=radio]')
    || el.closest?.('label')?.control
    || el;
  const kind = target.matches?.(FIELD) ? kindOf(target) : '';
  if (kind === 'check') return ['check', '', ownRequired(target)];
  const radio = kind === 'radio' ? target : target.querySelector?.(RADIOS);
  const required = requiredOf(target) || Boolean(radio && requiredOf(radio));
  return [kind === 'radio' ? 'radio' : '', radio ? groupOf(radio) : '', required];
}"""

# Опись видит родные поля формы и поля с ролями: самодельный виджет без роли ей
# не виден, его агент находит снимком страницы. Видимым считается и поле,
# спрятанное за своей видимой подписью: так сайты рисуют галочки и кружки.
# Неактивное поле заполнить нельзя, и в опись оно не идёт. Поле внутри самодельного с ролью
# — часть того, а не своё. Кружки одной группы — одна запись: выбирают вариант,
# а не кружок; кружок без группы стоит сам по себе. Подпись — без текста самого
# поля (у списка внутри метки это его варианты); у самодельного кружка и галочки
# подпись — их собственный текст.
#
# Селектор — по `id`, затем по единственному имени: так поле находится и после
# того, как страница перестроит разметку. Иначе поле получает метку
# `data-job-bot-field`, номера которой продолжают прежние: опись снимается на
# странице не раз, и новое поле не должно получить чужой номер.
_INVENTORY = "() => {" + _RULES + r"""
  const SKIP = ['hidden', 'submit', 'button', 'reset', 'image', 'file'];
  const OWNER = '[role=checkbox], [role=switch], [role=radio], [role=combobox]';
  const text = (node) => (node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
  const byIds = (ids) => (ids || '').split(/\s+/).map((id) => text(document.getElementById(id))).join(' ').trim();
  const bare = (node) => {
    if (!node) return '';
    const copy = node.cloneNode(true);
    copy.querySelectorAll(FIELD).forEach((one) => one.remove());
    return text(copy);
  };
  const labelOf = (el) => bare(el.labels?.[0]) || el.getAttribute('aria-label')?.trim()
    || byIds(el.getAttribute('aria-labelledby')) || el.getAttribute('placeholder')?.trim()
    || bare(el.closest('label')) || (el.matches(OWNER) && kindOf(el) !== 'select' ? text(el) : '');
  const taken = [...document.querySelectorAll('[data-job-bot-field]')].map((one) => Number(one.dataset.jobBotField));
  let marks = Math.max(0, ...taken);
  const selectorOf = (el) => {
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) return '#' + CSS.escape(el.id);
    const name = el.getAttribute('name');
    const byName = name && `${el.localName}[name="${CSS.escape(name)}"]`;
    if (byName && document.querySelectorAll(byName).length === 1) return byName;
    if (!el.dataset.jobBotField) el.dataset.jobBotField = String(++marks);
    return `[data-job-bot-field="${el.dataset.jobBotField}"]`;
  };
  const groupEntry = (el, key) => {
    const set = el.closest('fieldset');
    const whole = set && [...set.querySelectorAll(RADIOS)].every((one) => (groupOf(one) || one) === key);
    const box = el.closest('[role=radiogroup]') || (whole ? set : null);
    const label = box ? text(box.querySelector('legend')) || box.getAttribute('aria-label')?.trim()
      || byIds(box.getAttribute('aria-labelledby')) : '';
    const selector = el.closest('[role=radiogroup]') ? selectorOf(el.closest('[role=radiogroup]'))
      : el.name ? `input[name="${CSS.escape(el.name)}"]` : selectorOf(el);
    return [selector, label || '', 'radio', false, []];
  };
  const entries = [];
  const groups = new Map();
  const shown = (el) => el.getClientRects().length > 0
    || [...(el.labels || [])].some((one) => one.getClientRects().length > 0);
  const open = (el) => !el.disabled && el.getAttribute('aria-disabled') !== 'true';
  for (const el of document.querySelectorAll(FIELD)) {
    if (SKIP.includes((el.type || '').toLowerCase()) || !shown(el) || !open(el)) continue;
    if (el.parentElement?.closest(OWNER)) continue;
    const kind = kindOf(el);
    if (kind !== 'radio') {
      const options = el.localName === 'select'
        ? [...el.options].filter((one) => one.value !== '' && !one.disabled).map(text) : [];
      entries.push([selectorOf(el), labelOf(el), kind, requiredOf(el), options]);
      continue;
    }
    const key = groupOf(el) || el;
    if (!groups.has(key)) {
      groups.set(key, groupEntry(el, key));
      entries.push(groups.get(key));
    }
    const entry = groups.get(key);
    entry[3] = entry[3] || requiredOf(el);
    entry[4].push(labelOf(el));
  }
  return entries;
}"""


async def page_inventory(page) -> list[FieldEntry]:
    """Все видимые поля формы на странице, в порядке разметки."""
    return [FieldEntry(*entry) for entry in await page.evaluate(_INVENTORY)]


class PageField(NamedTuple):
    """Элемент страницы: вид (`check`, `radio` или пусто — не поле), группа
    кружка и обязательность."""

    kind: str
    group: str
    required: bool


async def page_field(page, selector: str) -> PageField:
    return PageField(*await page.locator(selector).first.evaluate(_FIELD_OF, timeout=WAIT_MS))


async def field_or_none(page, selector: str) -> PageField | None:
    """Поле, если оно сейчас на странице; иначе пусто — сразу, без ожидания.

    Подтверждённое на прошлом шаге формы того же адреса со страницы уходит, и
    ждать его срок значило бы платить им за каждое нажатие.
    """
    if not await page.locator(selector).count():
        logger.info("поле %s на странице не найдено", selector)
        return None
    return await page_field(page, selector)
