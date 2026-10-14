// @vitest-environment jsdom
//
// Доходят ли перечни от моста до подсказки в форме заведения.
//
// Между ответом моста и полем стоят экран, окно и сами поля. Каждое звено
// проверено порознь, и все три зелены — а в живом окне подсказка пуста, значит
// рвётся оно на стыке, которого порознь не видно.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import VacanciesScreen from '../app/VacanciesScreen.svelte';
import { hearRound } from '../state/round.svelte.js';
import { sectionMemory } from '../state/section_memory.svelte.js';
import { roundGoes } from './bridge_stub.js';
import { livingProps } from './live_props.svelte.js';
import { buttonBy, press } from './press.js';
import { settled } from './settled.js';

let mounted = null;
let host = null;

afterEach(() => {
  hearRound({ on: () => () => {} });
  if (mounted) flushSync(() => unmount(mounted));
  host?.remove();
  mounted = null;
  host = null;
});

const SENT = [];
const PASTED = [];
const SAID = [];

/** Мост, отвечающий тем же, чем отвечает настоящий.
 *
 * Заведение чужой карточки отказывает: так ведёт себя настоящий, когда имя
 * занято или связь оборвалась, — и это единственный способ увидеть, что
 * остаётся в черновике после неудачи.
 */
async function bridge(method, payload) {
  if (method === 'vacancies.create') {
    SENT.push(payload);
    return { created_id: 77 };
  }
  if (method === 'vacancies.create_from_text') {
    PASTED.push(payload);
    return { started: true };
  }
  if (method === 'companies.create' || method === 'hr.create') return null;
  if (method === 'vacancies.list') {
    return { vacancies: [], has_more: false, score_threshold: 5 };
  }
  if (method === 'vacancies.filter_options') {
    return { filter_options: { channels: [], companies: [] } };
  }
  if (method === 'vacancies.create_options') {
    return {
      hrs: [{ id: 1, name: 'Polyy' }, { id: 2, name: 'Yana' }],
      companies: [{ id: 3, name: 'Nitka' }],
    };
  }
  return null;
}

function screen() {
  SENT.length = 0;
  PASTED.length = 0;
  SAID.length = 0;
  const [props] = livingProps({
    ask: bridge,
    say: (text) => SAID.push(text),
    lockedTip: '',
    events: { on: () => () => {} },
    oncontacts: () => {},
    open: null,
    onopened: () => {},
    onchosen: () => {},
    openFilter: null,
    onfiltered: () => {},
    view: sectionMemory().views.vacancies,
    onview: () => {},
  });
  host = document.createElement('div');
  document.body.append(host);
  mounted = mount(VacanciesScreen, { target: host, props });
  return host;
}

/** Ряд пилюль с названной подписью: рядов в форме несколько, и различает их
 *  человек тоже подписью. */
function chipRow(page, caption) {
  return [...page.querySelectorAll('.captioned-field')].find(
    (one) => one.querySelector('.field-caption')?.textContent.trim() === caption,
  );
}

/** Набрать пилюлю в названном ряду так, как её набирают руками. */
async function typeChip(row, text) {
  row.querySelector('.chip-add').click();
  await settled();
  const input = row.querySelector('.chip-input');
  input.value = text;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }),
  );
  await settled();
}

describe('живой экран вакансий', () => {
  it('открытая форма подсказывает заведённых людей', async () => {
    const page = screen();
    await settled();

    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    const hr = page.querySelector('input[placeholder="HR"]');
    hr.dispatchEvent(new Event('focus'));
    await settled();

    expect(page.textContent).toContain('Polyy');
  });

  it('подсказка переживает то самое нажатие, которым её открыли', async () => {
    // Живое нажатие — это не один фокус: за ним всплывает `click`, а на
    // документе к этому мигу уже висит сторож «нажали мимо». Сочти он своим
    // это нажатие — панель закрывалась бы ровно тогда, когда её открывают, и
    // снаружи это выглядит как список, который не выпадает вовсе.
    const page = screen();
    await settled();

    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    const hr = page.querySelector('input[placeholder="HR"]');
    hr.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    hr.dispatchEvent(new Event('focus'));
    await settled();
    hr.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    hr.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await settled();

    expect(page.textContent).toContain('Polyy');
  });

  it('отказ заведения не оставляет вакансию привязанной к прежней карточке', async () => {
    // Человек выбрал «Nitka», передумал и набрал «Acme»; мост отказал. Останься
    // прежний номер — вакансия молча уехала бы к Nitka, а в поле стояло бы
    // «Acme»: такую ошибку не видно ни в форме, ни в списке.
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    const title = page.querySelector('input[placeholder="Название (обязательно)"]');
    title.value = 'Python-разработчик';
    title.dispatchEvent(new Event('input', { bubbles: true }));

    const company = page.querySelector('input[placeholder="Компания"]');
    company.dispatchEvent(new Event('focus'));
    company.value = 'Nitka';
    company.dispatchEvent(new Event('input', { bubbles: true }));
    company.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await settled();

    company.value = 'Acme';
    company.dispatchEvent(new Event('input', { bubbles: true }));
    company.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await settled();

    press('Создать', { exact: true });
    await settled();

    expect(SENT).toHaveLength(1);
    expect(SENT[0].company_id).toBe(null);
    expect(SENT[0].company_name).toBe('Acme');
  });

  it('пилюли двух рядов уезжают на мост двумя списками', async () => {
    // Ряды весят по-разному: незнакомое в основных отнимает балл, в
    // дополнительных не стоит ничего. Слейся они в один список по дороге,
    // вакансия получила бы чужой балл, и увидеть это в форме было бы нечем.
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    const title = page.querySelector('input[placeholder="Название (обязательно)"]');
    title.value = 'Python-разработчик';
    title.dispatchEvent(new Event('input', { bubbles: true }));

    await typeChip(chipRow(page, 'Must:'), 'Python');
    await typeChip(chipRow(page, 'Nice:'), 'Docker');

    press('Создать', { exact: true });
    await settled();

    expect(SENT[0].stack_required).toEqual(['Python']);
    expect(SENT[0].stack_preferred).toEqual(['Docker']);
  });

  it('вставленный текст уезжает своим слотом, а не полями формы', async () => {
    // Вкладки две, а слот у каждой свой: поля идут прямо в строку, текст — в
    // конвейер на разбор. Уедь текст слотом полей, вакансия завелась бы с
    // пустым названием и без разбора вовсе.
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    press('Текст', { exact: true });
    await settled();

    const text = page.querySelector('textarea[placeholder="Текст объявления"]');
    text.value = 'Ищем флориста в студию';
    text.dispatchEvent(new Event('input', { bubbles: true }));

    // Дату набирают тем же полем, что и на стороне полей; уедь она мимо
    // нагрузки, объявление выпало бы из отбора «за последние дни».
    const when = page.querySelector('.date-picker input');
    when.value = '20.08.2026';
    when.dispatchEvent(new Event('input', { bubbles: true }));
    await settled();

    press('Создать', { exact: true });
    await settled();

    expect(PASTED).toHaveLength(1);
    expect(PASTED[0].raw_text).toBe('Ищем флориста в студию');
    expect(PASTED[0].posted_at).toBe('2026-08-20');
    expect(SENT).toHaveLength(0);
    // Про исход говорит весть, когда разбор кончится. Скажи окно «Вакансия
    // заведена» сразу — на повторе и на молчащей модели человек прочёл бы
    // подтверждение раньше отказа, и первое было бы ложью.
    expect(SAID).toEqual([]);
  });

  it('на стороне полей окно подтверждает заведение словом', async () => {
    // Там работа кончается ответом моста, а не вестью: промолчи окно —
    // человек не понял бы, завелась ли вакансия.
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    const title = page.querySelector('input[placeholder="Название (обязательно)"]');
    title.value = 'Python-разработчик';
    title.dispatchEvent(new Event('input', { bubbles: true }));
    await settled();

    press('Создать', { exact: true });
    await settled();

    expect(SAID).toEqual(['Вакансия заведена']);
  });

  it('кнопка «Создать» на вкладке текста ждёт текста, а не названия', async () => {
    // Заслон у вкладок разный: полям нужно название, тексту — сам текст.
    // Останься заслон общим, кнопка на вкладке текста молчала бы всегда.
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    press('Текст', { exact: true });
    await settled();

    const create = buttonBy('Создать', { exact: true });
    expect(create.disabled).toBe(true);

    const text = page.querySelector('textarea[placeholder="Текст объявления"]');
    text.value = 'Ищем повара';
    text.dispatchEvent(new Event('input', { bubbles: true }));
    await settled();

    expect(create.disabled).toBe(false);
  });

  it('Escape в наборе пилюли отменяет пилюлю, а не форму', async () => {
    // Окно слушает Escape окном, а пилюля — своим полем. Не разбери они, кому
    // нажатие досталось, человек терял бы всю набранную форму, передумав
    // добавлять один скил.
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    chipRow(page, 'Must:').querySelector('.chip-add').click();
    await settled();

    const chip = page.querySelector('.chip-input');
    // Нажатие отменяемое — как у настоящего: на неотменяемом `preventDefault`
    // ничего не делает, и проверка зеленела бы мимо предмета.
    chip.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
    );
    await settled();

    expect(page.querySelector('input[placeholder="Название (обязательно)"]')).toBeTruthy();
  });

  it('во время обхода вставленный текст не заводится, и кнопка говорит почему', async () => {
    // Разбор вставленного занимает место прогона, и мост его не пустит.
    roundGoes();
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    press('Текст', { exact: true });
    await settled();
    const text = page.querySelector('textarea[placeholder="Текст объявления"]');
    text.value = 'Ищем повара';
    text.dispatchEvent(new Event('input', { bubbles: true }));
    await settled();

    const create = page.querySelector('.modal-footer .btn.primary');
    expect(create.textContent.trim()).toBe('Идёт обход');
    expect(create.disabled).toBe(true);
  });
});
