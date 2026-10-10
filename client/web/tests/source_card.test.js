// Карточка источника — канала или агрегатора: числа, вакансии и смена
// открытого источника.

import { describe, expect, it } from 'vitest';

import { sourceCard } from '$state/source_card.svelte.js';

import { listening } from './bridge_stub.js';

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

/** Карточка, чей мост отвечает по номеру источника и записывает вопросы. */
function opened(details) {
  const asked = [];
  const card = sourceCard({
    ask: async (method, id) => {
      asked.push([method, id]);
      return details[id] ?? null;
    },
    method: 'sources.detail',
    trouble: 'Не удалось прочитать источник',
    vacanciesOf: (id) => async (page) => {
      asked.push(['vacancies', id, page.offset]);
      return { vacancies: [{ id: id * 10 }], has_more: true };
    },
  });
  return { card, asked };
}

describe('карточка источника', () => {
  it('заход читает числа и вакансии открытого источника', async () => {
    const { card } = opened({ 7: { name: 'Семь' } });

    card.watch(listening(), 7);
    await settle();

    expect(card.card).toEqual({ name: 'Семь' });
    expect(card.vacancies.rows).toEqual([{ id: 70 }]);
  });

  it('смена источника сразу убирает показанное прежним', async () => {
    const { card } = opened({ 7: { name: 'Семь' } });
    card.watch(listening(), 7)();
    await settle();

    card.watch(listening(), 8);

    expect(card.card).toBe(null);
    expect(card.vacancies.rows).toEqual([]);
  });

  it('отказ моста показан строкой беды', async () => {
    const { card } = opened({});

    card.watch(listening(), 7);
    await settle();

    expect(card.trouble).toBe('Не удалось прочитать источник');
  });

  it('весть о смене вакансий перечитывает открытый источник', async () => {
    const events = listening();
    const { card, asked } = opened({ 7: { name: 'Семь' } });
    card.watch(events, 7);
    await settle();

    events.fire('vacancies_list_changed');
    await settle();

    expect(asked.filter(([what]) => what === 'sources.detail')).toHaveLength(2);
  });

  it('добор берёт следующую страницу открытого источника', async () => {
    const { card, asked } = opened({ 7: { name: 'Семь' } });
    card.watch(listening(), 7);
    await settle();

    await card.more(7);

    expect(asked.at(-1)).toEqual(['vacancies', 7, 1]);
  });
});
