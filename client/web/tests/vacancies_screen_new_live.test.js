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
import { hearAwaited } from '../state/awaited.svelte.js';
import { hearRound } from '../state/round.svelte.js';
import { heldMemory, sectionMemory } from '../state/section_memory.svelte.js';
import { settleHandMade } from '../state/vacancies.js';
import { awaitingNews, roundGoes } from './bridge_stub.js';
import { livingProps } from './live_props.svelte.js';
import { buttonBy, press, typed } from './press.js';
import { settled } from './settled.js';

let mounted = null;
let host = null;

afterEach(() => {
  hearRound({ on: () => () => {} });
  hearAwaited({ on: () => () => {} });
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
  if (method === 'vacancies.create' && payload.title === 'Повтор') {
    SENT.push(payload);
    return { created_id: 5, created: false, message: 'Такая вакансия уже существует' };
  }
  if (method === 'vacancies.create' && payload.hands_over) {
    SENT.push(payload);
    return { started: true, action: 'create_from_text' };
  }
  if (method === 'vacancies.create') {
    SENT.push(payload);
    return { created_id: 77, created: true, message: 'Вакансия заведена' };
  }
  if (method === 'vacancies.create_from_text' && payload.raw_text === 'Отказ') {
    PASTED.push(payload);
    return null;
  }
  if (method === 'vacancies.create_from_text' && payload.raw_text === 'Занято') {
    // Место прогона занято: отказ приходит вестью раньше ответа на сам зов.
    PASTED.push(payload);
    NEWS?.({ action: 'create_from_text', message: 'Идёт другой прогон', danger: true });
    return { started: true };
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

const OPENED = [];
// Доставка вести об исходе — как её доставляет оболочка: через учёт ожиданий.
let NEWS = null;

function screen({ lockedTip = '', memory = heldMemory() } = {}) {
  SENT.length = 0;
  PASTED.length = 0;
  SAID.length = 0;
  OPENED.length = 0;
  NEWS = awaitingNews().finished;
  const [props] = livingProps({
    ask: bridge,
    say: (text) => SAID.push(text),
    lockedTip,
    newVacancy: memory.newVacancy,
    // Итог принимает то же правило, что и оболочка.
    onhandmade: (news) => settleHandMade(memory.newVacancy, news),
    onvacancy: (id) => OPENED.push(id),
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
  typed(input, text);
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

    typed(page.querySelector('input[placeholder="Название (обязательно)"]'), 'Python-разработчик');

    const company = page.querySelector('input[placeholder="Компания"]');
    company.dispatchEvent(new Event('focus'));
    typed(company, 'Nitka');
    company.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await settled();

    typed(company, 'Acme');
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

    typed(page.querySelector('input[placeholder="Название (обязательно)"]'), 'Python-разработчик');

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

    typed(page.querySelector('textarea[placeholder="Текст объявления"]'), 'Ищем флориста в студию');

    // Дату набирают тем же полем, что и на стороне полей; уедь она мимо
    // нагрузки, объявление выпало бы из отбора «за последние дни».
    typed(page.querySelector('.date-picker input'), '20.08.2026');
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

  it('ссылка уезжает слотом текста одним адресом, а не полями', async () => {
    // Что за ссылкой — пост, статья, страница, — решает бот; окно отдаёт адрес
    // как есть и ждёт итога вестью, как у текста.
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    page.querySelector('.choice-line input[type="checkbox"]').click();
    press('Ссылка', { exact: true });
    await settled();

    typed(page.querySelector('input[placeholder="Ссылка на объявление"]'), 'https://t.me/pyjobs/5');
    await settled();
    press('Создать', { exact: true });
    await settled();

    expect(PASTED).toEqual([{ url: 'https://t.me/pyjobs/5', hands_over: true }]);
    expect(SENT).toHaveLength(0);
    expect(SAID).toEqual([]);
  });

  it('вкладка «Ссылка» и «Ссылка на объявление» у полей — одно поле черновика', async () => {
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    press('Ссылка', { exact: true });
    await settled();
    const create = buttonBy('Создать', { exact: true });
    expect(create.disabled).toBe(true);

    typed(page.querySelector('input[placeholder="Ссылка на объявление"]'), 'https://hh.ru/vacancy/1');
    await settled();
    expect(create.disabled).toBe(false);

    press('Поля', { exact: true });
    await settled();
    expect(page.querySelector('input[placeholder="Ссылка на объявление"]').value).toBe('https://hh.ru/vacancy/1');
  });

  it('без живых систем ссылка не заводится, как и текст', async () => {
    const page = screen({ lockedTip: 'Нужны все системы, сейчас недоступно: LLM.' });
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    press('Ссылка', { exact: true });
    await settled();
    typed(page.querySelector('input[placeholder="Ссылка на объявление"]'), 'https://hh.ru/vacancy/1');
    await settled();

    const create = page.querySelector('.modal-footer .btn.primary');
    expect(create.disabled).toBe(true);
    expect(create.textContent.trim()).toBe('Нужны все системы, сейчас недоступно: LLM.');
  });

  it('на стороне полей окно подтверждает заведение словом', async () => {
    // Там работа кончается ответом моста, а не вестью: промолчи окно —
    // человек не понял бы, завелась ли вакансия.
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    typed(page.querySelector('input[placeholder="Название (обязательно)"]'), 'Python-разработчик');
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

    typed(page.querySelector('textarea[placeholder="Текст объявления"]'), 'Ищем повара');
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

  it('галочка «Отклик при создании» стоит рядом с вкладками, выключена, с пояснением', async () => {
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    const box = page.querySelector('.choice-line input[type="checkbox"]');
    expect(box.checked).toBe(false);
    expect(box.title).toBe('Отклик при создании');
  });

  it('включённая галочка уезжает на мост с текстом', async () => {
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    page.querySelector('.choice-line input[type="checkbox"]').click();
    await settled();
    press('Текст', { exact: true });
    await settled();
    typed(page.querySelector('textarea[placeholder="Текст объявления"]'), 'Ищем повара');
    await settled();

    press('Создать', { exact: true });
    await settled();

    expect(PASTED[0].hands_over).toBe(true);
  });

  it('без живых систем галочка заперта и показана выключенной, а запомненное цело', async () => {
    const memory = heldMemory();
    memory.newVacancy.handsOver = true;
    const page = screen({ lockedTip: 'Нужны все системы, сейчас недоступно: LLM.', memory });
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    const box = page.querySelector('.choice-line input[type="checkbox"]');
    expect([box.checked, box.disabled]).toEqual([false, true]);
    expect(box.title).toBe('Нужны все системы, сейчас недоступно: LLM.');
    expect(memory.newVacancy.handsOver).toBe(true);
  });

  it('введённый текст доживает до итога: окно закрыто — открыто снова, а «Создать» заперта', async () => {
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    press('Текст', { exact: true });
    await settled();
    typed(page.querySelector('textarea[placeholder="Текст объявления"]'), 'Ищем повара');
    await settled();
    press('Создать', { exact: true });
    await settled();

    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    expect(page.querySelector('textarea[placeholder="Текст объявления"]').value).toBe('Ищем повара');
    expect(page.querySelector('.modal-footer .btn.primary').disabled).toBe(true);
  });

  /** Открыть окно на вкладке текста и набрать объявление. */
  async function typedText(page, words) {
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    press('Текст', { exact: true });
    await settled();
    typed(page.querySelector('textarea[placeholder="Текст объявления"]'), words);
    await settled();
  }

  it('отказ, пришедший вестью раньше ответа, черновика не стирает', async () => {
    const page = screen();
    await settled();
    await typedText(page, 'Занято');

    press('Создать', { exact: true });
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    expect(page.querySelector('textarea[placeholder="Текст объявления"]').value).toBe('Занято');
    expect(page.querySelector('.modal-footer .btn.primary').disabled).toBe(false);
  });

  it('после неудачи открытое и закрытое окно черновик стирает', async () => {
    // Неудача оставляет набранное до следующего захода; но закрыл окно сам,
    // ничего не отправив, — набранное больше не нужно, как у любого окна.
    const page = screen();
    await settled();
    await typedText(page, 'Занято');
    press('Создать', { exact: true });
    await settled();

    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    press('Отмена', { exact: true });
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    press('Текст', { exact: true });
    await settled();

    expect(page.querySelector('textarea[placeholder="Текст объявления"]').value).toBe('');
  });

  it('неудача при открытом снова окне — «Отмена» черновик стирает', async () => {
    // Окно открыли, пока ждали итог; неудача пришла при открытом — дальше оно
    // такое же, как открытое после неудачи.
    const page = screen();
    await settled();
    await typedText(page, 'Ищем повара');
    press('Создать', { exact: true });
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    NEWS({ action: 'create_from_text', outcome: 'error', message: 'Модель не ответила', danger: true });
    await settled();
    press('Отмена', { exact: true });
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    press('Текст', { exact: true });
    await settled();

    expect(page.querySelector('textarea[placeholder="Текст объявления"]').value).toBe('');
  });

  it('после неудачи заведённые напрямую поля черновик не оставляют', async () => {
    const page = screen();
    await settled();
    await typedText(page, 'Занято');
    press('Создать', { exact: true });
    await settled();

    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    press('Поля', { exact: true });
    await settled();
    typed(page.querySelector('input[placeholder="Название (обязательно)"]'), 'Python');
    await settled();
    press('Создать', { exact: true });
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();

    expect(page.querySelector('input[placeholder="Название (обязательно)"]').value).toBe('');
  });

  it('отказ зова снимает ожидание: «Создать» снова доступна', async () => {
    const page = screen();
    await settled();
    await typedText(page, 'Отказ');

    press('Создать', { exact: true });
    await settled();

    expect(page.querySelector('.modal-footer .btn.primary').disabled).toBe(false);
  });

  it('поля с галочкой уходят боту с просьбой отклика', async () => {
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    page.querySelector('.choice-line input[type="checkbox"]').click();
    typed(page.querySelector('input[placeholder="Название (обязательно)"]'), 'Python');
    await settled();

    press('Создать', { exact: true });
    await settled();

    expect(SENT[0].hands_over).toBe(true);
    // Слово скажет весть: ответ «пущено» ничего не заводит.
    expect(SAID).toEqual([]);
  });

  it('повтор у полей переводит на существующую вакансию и говорит это словами', async () => {
    const page = screen();
    await settled();
    page.querySelector('button[title="Добавить вакансию"]').click();
    await settled();
    typed(page.querySelector('input[placeholder="Название (обязательно)"]'), 'Повтор');
    await settled();

    press('Создать', { exact: true });
    await settled();

    expect(OPENED).toEqual([5]);
    expect(SAID).toEqual(['Такая вакансия уже существует']);
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
    typed(page.querySelector('textarea[placeholder="Текст объявления"]'), 'Ищем повара');
    await settled();

    const create = page.querySelector('.modal-footer .btn.primary');
    expect(create.textContent.trim()).toBe('Идёт обход');
    expect(create.disabled).toBe(true);
  });
});
