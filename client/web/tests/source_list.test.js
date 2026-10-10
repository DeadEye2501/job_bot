// Список источников вакансий — каналов или агрегаторов: чтение с поиском,
// строчный и общий переключатели.

import { describe, expect, it } from 'vitest';

import { sourceList } from '$state/source_list.svelte.js';

const ALIVE = { now: true, entered: (read) => (read(), () => {}) };

function answer(rows, extra = {}) {
  return { sources: rows, enabled: true, ...extra };
}

/** Список, читающий заготовленные ответы и записывающий, что у моста просили. */
function listing(answers, calls = {}) {
  const asked = [];
  const list = sourceList({
    alive: ALIVE,
    key: 'sources',
    read: async (search) => {
      asked.push(search);
      return answers.shift();
    },
    setActive: calls.setActive ?? (async () => ({})),
    setAll: calls.setAll ?? (async () => ({})),
  });
  return { list, asked };
}

describe('список источников', () => {
  it('до первого ответа не прочитан, после — показывает строки и общий выключатель', async () => {
    const { list } = listing([answer([{ id: 1 }], { enabled: false })]);
    expect(list.loaded).toBe(false);

    await list.again();

    expect(list.loaded).toBe(true);
    expect(list.rows).toEqual([{ id: 1 }]);
    expect(list.enabled).toBe(false);
  });

  it('поиск запоминается и уходит в чтение', async () => {
    const { list, asked } = listing([answer([])]);

    await list.find('jobs');

    expect(list.search).toBe('jobs');
    expect(asked).toEqual(['jobs']);
  });

  it('ответ, обогнанный свежим, не ложится поверх', async () => {
    // Поиск набирают посимвольно, и ответы доезжают вразнобой.
    let late;
    const answers = [null, answer([{ id: 2 }])];
    const list = sourceList({
      alive: ALIVE,
      key: 'sources',
      read: () => {
        const next = answers.shift();
        return next === null ? new Promise((resolve) => (late = resolve)) : Promise.resolve(next);
      },
      setActive: async () => ({}),
      setAll: async () => ({}),
    });

    const first = list.find('j');
    await list.find('jo');
    late(answer([{ id: 1 }]));
    await first;

    expect(list.rows).toEqual([{ id: 2 }]);
  });

  it('переключатель строки говорит, легло ли, и список перечитан', async () => {
    const { list, asked } = listing([answer([]), answer([])], { setActive: async () => null });

    expect(await list.toggle({ id: 1 }, true)).toBe(false);
    expect(asked).toHaveLength(1);
  });

  it('общий выключатель уходит своим зовом и говорит, легло ли', async () => {
    const sent = [];
    const { list } = listing([answer([])], { setAll: async (on) => (sent.push(on), {}) });

    expect(await list.toggleAll(false)).toBe(true);
    expect(sent).toEqual([false]);
  });

  it('заход на вкладку читает список', async () => {
    const { list, asked } = listing([answer([{ id: 1 }])]);

    list.entered();
    await Promise.resolve();

    expect(asked).toEqual(['']);
  });
});
