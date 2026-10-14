// Что окно помнит о разделах, пока открыто: вкладку и открытую карточку.
//
// Вернувшись в раздел, человек видит то же, где был. Сменил вкладку — карточка
// прежней вкладки забывается: чужой номер новая вкладка приняла бы за свой.

import { describe, expect, it } from 'vitest';

import { sectionMemory, withCard, withTab } from '../state/section_memory.svelte.js';

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

  it('та же вкладка карточку не трогает', () => {
    const before = withCard(sectionMemory(), 'contacts', { tab: 'channels', id: 3 });

    const after = withTab(before, 'contacts', 'channels');

    expect(after.cards.contacts).toEqual({ tab: 'channels', id: 3 });
  });
});
