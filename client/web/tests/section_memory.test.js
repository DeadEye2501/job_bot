// Что окно помнит о разделах, пока открыто: вкладку и открытую карточку.
//
// Вернувшись в раздел, человек видит то же, где был. Сменил вкладку — карточка
// прежней вкладки забывается: чужой номер новая вкладка приняла бы за свой.

import { describe, expect, it } from 'vitest';

import {
  heldMemory,
  sectionMemory,
  withCard,
  withTab,
  withView,
} from '../state/section_memory.svelte.js';
import { blankVacancy } from '../state/vacancies.js';

describe('заведение вакансии в памяти окна', () => {
  it('в свежем окне отклик при создании выключен, а черновик пуст', () => {
    const memory = heldMemory();

    expect(memory.newVacancy.handsOver).toBe(false);
    expect(memory.newVacancy.draft).toEqual(blankVacancy());
  });

  it('включённый отклик и набранное живут, пока живёт окно', () => {
    const memory = heldMemory();

    memory.newVacancy.handsOver = true;
    memory.newVacancy.draft.title = 'Python';

    expect([memory.newVacancy.handsOver, memory.newVacancy.draft.title]).toEqual([true, 'Python']);
  });
});

describe('память разделов', () => {
  it('открытая карточка помнится по разделу', () => {
    const memory = withCard(sectionMemory(), 'contacts', { tab: 'channels', id: 3 });

    expect(memory.cards.contacts).toEqual({ tab: 'channels', id: 3 });
    expect(memory.cards.vacancies ?? null).toBeNull();
  });

  it('другая вкладка забывает карточку раздела', () => {
    const before = withCard(sectionMemory(), 'contacts', { tab: 'channels', id: 3 });

    const after = withTab(before, 'contacts', 'aggregators');

    expect([after.tabs.contacts, after.cards.contacts]).toEqual(['aggregators', null]);
  });

  it('смена вкладки не трогает отбор и порядок вакансий', () => {
    const view = { filter: { statuses: ['New'] }, sort: 'Сначала старые' };
    const before = withView(sectionMemory(), 'vacancies', view);

    const after = withTab(before, 'contacts', 'aggregators');

    expect(after.views.vacancies).toEqual(view);
  });

  it('та же вкладка карточку не трогает', () => {
    const before = withCard(sectionMemory(), 'contacts', { tab: 'channels', id: 3 });

    const after = withTab(before, 'contacts', 'channels');

    expect(after.cards.contacts).toEqual({ tab: 'channels', id: 3 });
  });
});
