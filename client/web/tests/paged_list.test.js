// Следствия списка, читающего себя страницами.
//
// Мост подделан: предмет здесь не он, а правила — что берётся страницей, что
// дописывается, чей ответ считается устаревшим и когда список молчит.

import { describe, expect, it } from 'vitest';

import { pagedList } from '$state/paged_list.svelte.js';

/** Подставной мост, отвечающий заготовленным и помнящий, о чём спрашивали. */
function bridge(pages) {
  const asked = [];
  const answer = async (method, payload) => {
    asked.push({ method, ...payload });
    const next = pages.shift();
    return typeof next === 'function' ? next() : next;
  };
  return { asked, answer };
}

function page(rows, has_more = false) {
  return { hrs: rows, has_more };
}

/** Прокрутка, доехавшая до низа списка. */
function atBottom() {
  return { currentTarget: { scrollTop: 1000, clientHeight: 100, scrollHeight: 1100 } };
}

describe('список страницами', () => {
  it('первое чтение берёт страницу с начала', async () => {
    const { asked, answer } = bridge([page([{ id: 1 }])]);
    const list = pagedList({ ask: answer, method: 'hr.list', key: 'hrs' });

    await list.refresh();

    expect(asked).toEqual([{ method: 'hr.list', search: '', limit: 50, offset: 0 }]);
    expect(list.rows).toEqual([{ id: 1 }]);
    expect(list.loaded).toBe(true);
  });

  it('до первого ответа список не считается прочитанным', () => {
    // Иначе окно показало бы «никого нет» вместо «идёт чтение».
    const list = pagedList({ ask: async () => null, method: 'hr.list', key: 'hrs' });

    expect(list.loaded).toBe(false);
  });

  it('поиск начинает список заново и запоминается', async () => {
    const { asked, answer } = bridge([page([{ id: 2 }])]);
    const list = pagedList({ ask: answer, method: 'hr.list', key: 'hrs' });

    await list.find('Мария');

    expect(asked[0].search).toBe('Мария');
    expect(asked[0].offset).toBe(0);
    expect(list.search).toBe('Мария');
  });

  it('перечитывание не схлопывает пролистанное', async () => {
    // Человек, стоящий на четвёртой сотне, иначе отбрасывался бы в начало
    // каждой правкой в карточке.
    const many = Array.from({ length: 120 }, (_, i) => ({ id: i }));
    const { asked, answer } = bridge([page(many), page(many)]);
    const list = pagedList({ ask: answer, method: 'hr.list', key: 'hrs' });

    await list.refresh(120);
    await list.again();

    expect(asked[1].limit).toBe(120);
  });

  it('отказ моста не стирает уже показанное', async () => {
    // Мост отвечает пустотой на любую беду, и стёртый на ней список читался бы
    // как «никого нет».
    const { answer } = bridge([page([{ id: 1 }]), null]);
    const list = pagedList({ ask: answer, method: 'hr.list', key: 'hrs' });

    await list.refresh();
    await list.refresh();

    expect(list.rows).toEqual([{ id: 1 }]);
  });

  it('ответ, доехавший после ухода с вкладки, никуда не ложится', async () => {
    // Строки, положенные в снесённое состояние, всплыли бы при следующем заходе
    // вперемешку со свежими.
    const { answer } = bridge([page([{ id: 1 }])]);
    const list = pagedList({ ask: answer, method: 'hr.list', key: 'hrs' });
    const settled = list.mounted();

    settled();
    await list.refresh();

    expect(list.rows).toEqual([]);
  });

  it('догрузка не обесценивает идущий поиск и не дописывает чужих строк', async () => {
    // Человек набрал поиск и продолжил прокручивать: страница просится от
    // старого списка, а ответ на поиск уже в пути. Победи догрузка — под
    // строкой «ivan» лежали бы полсотни посторонних людей, а найденное по
    // самому поиску отбросилось бы как устаревшее.
    const strangers = Array.from({ length: 50 }, (_, at) => ({ id: at }));
    let answerSearch;
    const { answer } = bridge([
      page(strangers, true),
      () => new Promise((resolve) => (answerSearch = resolve)),
      page([{ id: 900 }], true),
    ]);
    const list = pagedList({ ask: answer, method: 'hr.list', key: 'hrs' });

    await list.refresh();
    const searching = list.find('ivan');
    await list.scrolled(atBottom());
    answerSearch(page([{ id: 100 }], true));
    await searching;

    expect(list.rows).toEqual([{ id: 100 }]);
  });

  it('страница, доехавшая после перечитывания, к новому списку не дописывается', async () => {
    // Перечитывание кладёт другой список — правленые строки, свежий порядок, —
    // и дописывать к его хвосту страницу, отсчитанную от прежнего, значит
    // показать половину списка дважды.
    const strangers = Array.from({ length: 50 }, (_, at) => ({ id: at }));
    let answerMore;
    const { answer } = bridge([
      page(strangers, true),
      () => new Promise((resolve) => (answerMore = resolve)),
      page(strangers.slice(), true),
    ]);
    const list = pagedList({ ask: answer, method: 'hr.list', key: 'hrs' });

    await list.refresh();
    const loading = list.scrolled(atBottom());
    await list.refresh();
    answerMore(page([{ id: 900 }], true));
    await loading;

    expect(list.rows.map((one) => one.id)).not.toContain(900);
  });

  it('устаревший ответ уступает свежему', async () => {
    // Пока летел ответ по первому запросу, человек набрал ещё знак; доехав
    // вторым, старый ответ показал бы найденное по прежнему запросу.
    let releaseFirst;
    const first = new Promise((resolve) => (releaseFirst = resolve));
    const { answer } = bridge([() => first, page([{ id: 2 }])]);
    const list = pagedList({ ask: answer, method: 'hr.list', key: 'hrs' });

    const slow = list.find('М');
    await list.find('Ма');
    releaseFirst(page([{ id: 1 }]));
    await slow;

    expect(list.rows).toEqual([{ id: 2 }]);
  });
});
