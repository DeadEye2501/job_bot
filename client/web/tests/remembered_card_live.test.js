// @vitest-environment jsdom
//
// Открытая карточка переживает уход из раздела: экран раздела говорит наружу,
// чья карточка сейчас открыта, а вернувшись, получает её обратно той же разовой
// отметкой, что приходит со стороны.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import ContactsScreen from '../app/ContactsScreen.svelte';
import VacanciesScreen from '../app/VacanciesScreen.svelte';
import { hearRound } from '../state/round.svelte.js';
import { heldMemory } from '../state/section_memory.svelte.js';
import { settled } from './settled.js';

afterEach(() => {
  cleanup();
  hearRound({ on: () => () => {} });
});

const quiet = {
  say: () => {},
  lockedTip: '',
  events: { on: () => () => {} },
  onopened: () => {},
};

async function contacts(openCard) {
  const chosen = [];
  render(ContactsScreen, {
    props: {
      ...quiet,
      ask: async () => null,
      openCard,
      onvacancy: () => {},
      // Вкладку по отметке переключает оболочка; здесь её нет, и вкладка сразу та.
      tab: openCard.tab,
      ontab: () => {},
      onchosen: (card) => chosen.push(card),
    },
  });
  await settled();
  return chosen;
}

describe('контакты говорят, чья карточка открыта', () => {
  it('открытый канал', async () => {
    const chosen = await contacts({ tab: 'channels', id: 3 });

    expect(chosen.at(-1)).toEqual({ tab: 'channels', id: 3 });
  });

  it('открытая компания', async () => {
    const chosen = await contacts({ tab: 'companies', id: 5 });

    expect(chosen.at(-1)).toEqual({ tab: 'companies', id: 5 });
  });
});

describe('экран и настоящая память разделов', () => {
  it('открытая вакансия запоминается без бесконечного круга', async () => {
    const memory = heldMemory();
    render(VacanciesScreen, {
      props: {
        ...quiet,
        ask: async (method) =>
          method === 'vacancies.list' ? { vacancies: [], has_more: false, score_threshold: 5 } : null,
        oncontacts: () => {},
        open: { id: 9 },
        openFilter: null,
        onfiltered: () => {},
        onchosen: memory.remember('vacancies'),
      },
    });
    await settled();

    expect(memory.cards.vacancies).toEqual({ id: 9 });
  });
});

describe('вакансии говорят, чья карточка открыта', () => {
  it('открытая вакансия', async () => {
    const chosen = [];
    render(VacanciesScreen, {
      props: {
        ...quiet,
        ask: async (method) =>
          method === 'vacancies.list' ? { vacancies: [], has_more: false, score_threshold: 5 } : null,
        oncontacts: () => {},
        open: { id: 9 },
        openFilter: null,
        onfiltered: () => {},
        onchosen: (id) => chosen.push(id),
      },
    });
    await settled();

    expect(chosen.at(-1)).toEqual({ id: 9 });
  });
});
