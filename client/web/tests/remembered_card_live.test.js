// @vitest-environment jsdom
//
// Открытая карточка переживает уход из раздела: экран раздела говорит наружу,
// чья карточка сейчас открыта, а вернувшись, получает её обратно той же разовой
// отметкой, что приходит со стороны.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import ContactsScreen from '../app/ContactsScreen.svelte';
import VacanciesScreen from '../app/VacanciesScreen.svelte';
import { hearRound } from '../state/round.svelte.js';
import { heldMemory, sectionMemory } from '../state/section_memory.svelte.js';
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
        view: memory.views.vacancies,
        onview: memory.keepView('vacancies'),
      },
    });
    await settled();

    expect(memory.cards.vacancies).toEqual({ id: 9 });
  });
});

describe('порядок вакансий живёт в памяти разделов', () => {
  async function vacancies(memory) {
    const sorts = [];
    render(VacanciesScreen, {
      props: {
        ...quiet,
        ask: async (method, args) => {
          if (method !== 'vacancies.list') return null;
          sorts.push(args.sort);
          return { vacancies: [], has_more: false, score_threshold: 5 };
        },
        oncontacts: () => {},
        open: null,
        openFilter: null,
        onfiltered: () => {},
        onchosen: () => {},
        view: memory.views.vacancies,
        onview: memory.keepView('vacancies'),
      },
    });
    await settled();
    return sorts;
  }

  it('выбранный порядок переживает уход из раздела', async () => {
    const memory = heldMemory();
    await vacancies(memory);
    await fireEvent.click(screen.getByTitle(/^Сортировка:/));
    await fireEvent.click(screen.getByText('Сначала старые'));
    cleanup();

    const sorts = await vacancies(memory);

    expect(sorts.at(-1)).toBe('oldest');
  });

  it('свежее окно начинает с первого порядка', async () => {
    const before = heldMemory();
    await vacancies(before);
    await fireEvent.click(screen.getByTitle(/^Сортировка:/));
    await fireEvent.click(screen.getByText('Сначала старые'));
    cleanup();

    const sorts = await vacancies(heldMemory());

    expect(sorts.at(-1)).toBe('newest');
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
        view: sectionMemory().views.vacancies,
        onview: () => {},
      },
    });
    await settled();

    expect(chosen.at(-1)).toEqual({ id: 9 });
  });
});
