// Вакансии в карточке источника — канала или агрегатора: страницы, добор и
// перечитывание показанного.

import { describe, expect, it } from 'vitest';

import { sourceVacancies } from '$state/source_vacancies.svelte.js';

import { held } from './bridge_stub.js';

const ALIVE = { now: true };

function rows(from, count) {
  return Array.from({ length: count }, (_, at) => ({ id: from + at }));
}

/** Чтение, отвечающее страницами по очереди и записывающее, что просили. */
function reading(pages) {
  const asked = [];
  const read = async (page) => {
    asked.push(page);
    return pages.shift();
  };
  return { asked, read };
}

describe('вакансии источника', () => {
  it('первое чтение берёт страницу с начала', async () => {
    const list = sourceVacancies(ALIVE);
    const { asked, read } = reading([{ vacancies: rows(0, 3), has_more: false }]);

    await list.reload(read);

    expect(asked).toEqual([{ limit: 50, offset: 0 }]);
    expect(list.rows.map((one) => one.id)).toEqual([0, 1, 2]);
  });

  it('добор берёт страницу с конца показанного и дописывает её', async () => {
    const list = sourceVacancies(ALIVE);
    const { asked, read } = reading([
      { vacancies: rows(0, 50), has_more: true },
      { vacancies: rows(50, 2), has_more: false },
    ]);

    await list.reload(read);
    await list.more(read);

    expect(asked[1]).toEqual({ limit: 50, offset: 50 });
    expect(list.rows).toHaveLength(52);
  });

  it('добора нет, когда мост сказал, что больше нечего', async () => {
    const list = sourceVacancies(ALIVE);
    const { asked, read } = reading([{ vacancies: rows(0, 3), has_more: false }]);

    await list.reload(read);
    await list.more(read);

    expect(asked).toHaveLength(1);
  });

  it('перечитывание берёт столько, сколько показано, а не страницу', async () => {
    // Весть приходит на каждое разобранное объявление: страницей она схлопывала
    // бы пролистанное во время того самого прогона, который человек запустил.
    const list = sourceVacancies(ALIVE);
    const { asked, read } = reading([
      { vacancies: rows(0, 50), has_more: true },
      { vacancies: rows(50, 30), has_more: true },
      { vacancies: rows(0, 80), has_more: true },
    ]);

    await list.reload(read);
    await list.more(read);
    await list.reload(read);

    expect(asked[2]).toEqual({ limit: 80, offset: 0 });
  });

  it('ответ про прежний источник, доехавший последним, не ложится поверх свежего', async () => {
    // Источник сменяют нажатием по соседней строке, а ответы моста доезжают
    // вразнобой.
    const list = sourceVacancies(ALIVE);
    const late = held();
    const fresh = async () => ({ vacancies: rows(100, 1), has_more: false });

    const first = list.reload(() => late.promise);
    await list.reload(fresh);
    late.give({ vacancies: rows(0, 3), has_more: true });
    await first;

    expect(list.rows.map((one) => one.id)).toEqual([100]);
  });

  it('добор, пока летит прежний, второго запроса не шлёт', async () => {
    const list = sourceVacancies(ALIVE);
    const { read } = reading([{ vacancies: rows(0, 50), has_more: true }]);
    await list.reload(read);
    let asked = 0;
    const answer = held();
    const slow = () => {
      asked += 1;
      return answer.promise;
    };

    const first = list.more(slow);
    await list.more(slow);
    answer.give({ vacancies: rows(50, 1), has_more: false });
    await first;

    expect(asked).toBe(1);
  });

  it('сброс убирает показанное прежним источником', async () => {
    const list = sourceVacancies(ALIVE);
    const { read } = reading([{ vacancies: rows(0, 50), has_more: true }]);

    await list.reload(read);
    list.clear();

    expect(list.rows).toEqual([]);
    expect(list.hasMore).toBe(false);
  });
});
