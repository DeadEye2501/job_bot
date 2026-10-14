// @vitest-environment jsdom
//
// Карточка агрегатора: блок резюме человека на сайте и пункт «Обновить резюме»
// в меню действий.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import AggregatorCard from '../app/AggregatorCard.svelte';
import { hearRound } from '../state/round.svelte.js';
import { answering, roundGoes } from './bridge_stub.js';
import { settled } from './settled.js';
import { EMPTY_STATS } from './stats_stub.js';

afterEach(() => {
  cleanup();
  hearRound({ on: () => () => {} });
});

function cardOf(over) {
  return {
    aggregator_id: 4,
    name: 'HeadHunter',
    host: 'hh.ru',
    is_active: false,
    is_logged_in: true,
    is_web_search: false,
    avatar: null,
    blacklist_value: null,
    stats: EMPTY_STATS,
    resumes: [
      { id: 11, title: 'Повар', url: 'https://hh.ru/resume/11', chosen: false },
      { id: 12, title: 'Дизайнер', url: 'https://hh.ru/resume/12', chosen: true },
    ],
    can_add_resume: false,
    ...over,
  };
}

async function screen(over = {}) {
  const card = cardOf(over);
  const { asked, ask } = answering((method) =>
    method === 'aggregators.detail' ? card : { vacancies: [], has_more: false },
  );
  const shown = render(AggregatorCard, {
    props: {
      ask,
      say: () => {},
      lockedTip: '',
      lock: null,
      events: { on: () => () => {} },
      aggregatorId: card.aggregator_id,
      onvacancy: () => {},
      onclose: () => {},
      onchanged: () => {},
    },
  });
  await settled();
  return { asked, shown };
}

async function scanItem(shown) {
  shown.container.querySelector('button[title="Действия"]').click();
  await settled();
  return [...document.querySelectorAll('.menu-item')].find((one) =>
    one.textContent.includes('Обновить резюме'),
  );
}

describe('блок резюме в карточке агрегатора', () => {
  it('показывает резюме в порядке сайта и отмечает выбранное', async () => {
    const { shown } = await screen();
    const rows = [...shown.container.querySelectorAll('.resume-row')];

    expect(rows.map((one) => one.textContent.trim())).toEqual(['Повар', 'Дизайнер']);
    expect(rows.map((one) => one.querySelector('input[type="radio"]').checked)).toEqual([
      false,
      true,
    ]);
  });

  it('кружок отмечает резюме через мост', async () => {
    const { asked, shown } = await screen();

    shown.container.querySelectorAll('.resume-row input[type="radio"]')[0].click();
    await settled();

    expect(asked).toContainEqual({
      method: 'aggregators.choose_resume',
      payload: { aggregator_id: 4, resume_id: 11 },
    });
  });

  it('кружок показывает отметку базы, а не нажатие', async () => {
    const { shown } = await screen();
    const radios = shown.container.querySelectorAll('.resume-row input[type="radio"]');

    radios[0].click();
    await settled();

    // Прежний кружок группы после отменённого нажатия возвращает браузер; jsdom
    // этого не умеет, поэтому смотрим только на нажатый.
    expect(radios[0].checked).toBe(false);
  });

  it('название открывает страницу резюме в браузере', async () => {
    const { asked, shown } = await screen();

    shown.container.querySelectorAll('.resume-row button')[1].click();
    await settled();

    expect(asked).toContainEqual({ method: 'system.open_url', payload: 'https://hh.ru/resume/12' });
  });

  it('пустой блок называет сайт', async () => {
    const { shown } = await screen({ resumes: [] });

    expect(shown.container.textContent).toContain('Ваши резюме на HeadHunter появятся здесь');
  });
});

describe('пункт «Обновить резюме»', () => {
  it('без входа неактивен и просит войти', async () => {
    const { shown } = await screen({ is_logged_in: false });
    const item = await scanItem(shown);

    expect([item.disabled, item.title]).toEqual([true, 'Сначала войдите на сайт']);
  });

  it('со входом зовёт пересканирование', async () => {
    const { asked, shown } = await screen();
    const item = await scanItem(shown);

    item.click();
    await settled();

    expect(item.disabled).toBe(false);
    expect(asked).toContainEqual({ method: 'aggregators.scan', payload: 4 });
  });

  it('во время обхода неактивен и называет обход', async () => {
    roundGoes();
    const { shown } = await screen();
    const item = await scanItem(shown);

    expect([item.disabled, item.title]).toEqual([true, 'Идёт обход']);
  });
});
