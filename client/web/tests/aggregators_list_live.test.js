// @vitest-environment jsdom
//
// Вкладка «Агрегаторы», когда показывать нечего.
//
// Пустой список без поиска — это «ещё не заводили», а не «не нашлось»: подпись
// про запрос с пустыми кавычками отправила бы человека искать то, чего он не
// искал.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import AggregatorsList from '../app/AggregatorsList.svelte';
import { settled } from './settled.js';

afterEach(cleanup);

/** Вкладка над мостом, у которого агрегаторов нет: ни всех, ни по запросу. */
function screen() {
  const shown = render(AggregatorsList, {
    props: {
      ask: async (method, payload) =>
        method === 'aggregators.list'
          ? { aggregators: [], enabled: true, search: payload.search ?? '', lock: null }
          : null,
      say: () => {},
      lockedTip: '',
      events: { on: () => () => {} },
      open: null,
      onopened: () => {},
      onvacancy: () => {},
    },
  });
  return {
    text: () => shown.container.textContent,
    field: () => shown.container.querySelector('.search-input'),
  };
}

describe('пустая вкладка агрегаторов', () => {
  it('без поиска говорит, что агрегаторов ещё нет', async () => {
    const { text } = screen();
    await settled();

    expect(text()).toContain('Агрегаторов пока нет');
    expect(text()).not.toContain('Ничего не найдено');
  });

  it('с поиском говорит, что по запросу ничего не нашлось', async () => {
    const { text, field } = screen();
    await settled();

    field().value = 'работа';
    field().dispatchEvent(new Event('input', { bubbles: true }));
    await settled();

    expect(text()).toContain('Ничего не найдено по запросу «работа»');
    expect(text()).not.toContain('Агрегаторов пока нет');
  });
});
