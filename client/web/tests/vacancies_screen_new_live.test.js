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
import { livingProps } from './live_props.svelte.js';
import { settled } from './settled.js';

let mounted = null;
let host = null;

afterEach(() => {
  if (mounted) flushSync(() => unmount(mounted));
  host?.remove();
  mounted = null;
  host = null;
});

const SENT = [];

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
  const [props] = livingProps({
    ask: bridge,
    say: () => {},
    lockedTip: '',
    events: { on: () => () => {} },
    oncontacts: () => {},
    open: null,
    onopened: () => {},
    openFilter: null,
    onfiltered: () => {},
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

    [...page.querySelectorAll('button')].find((one) => one.textContent.trim() === 'Создать').click();
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

    [...page.querySelectorAll('button')].find((one) => one.textContent.trim() === 'Создать').click();
    await settled();

    expect(SENT[0].stack_required).toEqual(['Python']);
    expect(SENT[0].stack_preferred).toEqual(['Docker']);
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
});
