// @vitest-environment jsdom
//
// Карточка вакансии, которой сменили номер записи.
//
// Панель одна на весь список: выбор другой строки не заводит компонент заново,
// а меняет ему одно свойство. Не назови эффект этот номер своей зависимостью —
// на экране осталась бы прежняя вакансия, и человек правил бы статус не той.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import VacancyCard from '../app/VacancyCard.svelte';
import { livingProps } from './live_props.svelte.js';
import { settled } from './settled.js';

let mounted = null;
let host = null;

afterEach(() => {
  if (mounted) flushSync(() => unmount(mounted));
  host?.remove();
  mounted = null;
  host = null;
});

/** Карточка, какой её отдаёт мост: заполнено только то, что видно на экране. */
function detail(id) {
  return {
    id,
    status: 'New',
    title: `Вакансия ${id}`,
    description: null,
    score: null,
    score_threshold: 5,
    stack: [],
    history: [],
    events: [],
    hr: null,
    company_id: null,
    company_name: null,
    notes: '',
    raw_text: '',
    source_url: null,
    channel_username: null,
    posted_at: null,
    created_at: null,
    grade: null,
    salary: null,
    remote: null,
    location: null,
  };
}

function screen(vacancyId) {
  const asked = [];
  const [props, change] = livingProps({
    ask: async (method, payload) => {
      asked.push([method, payload]);
      return { vacancy: detail(payload) };
    },
    say: () => {},
    events: { on: () => () => {} },
    lockedTip: '',
    vacancyId,
    oncontacts: () => {},
    onclose: () => {},
    onchanged: () => {},
  });
  host = document.createElement('div');
  document.body.append(host);
  mounted = mount(VacancyCard, { target: host, props });
  return { asked, change, text: () => host.textContent };
}

describe('живая карточка вакансии', () => {
  it('перечитывается, когда открыли другую вакансию', async () => {
    const { asked, change, text } = screen(7);
    await settled();
    expect(asked).toEqual([['vacancies.detail', 7]]);

    change('vacancyId', 8);
    await settled();

    expect(asked).toEqual([
      ['vacancies.detail', 7],
      ['vacancies.detail', 8],
    ]);
    expect(text()).toContain('Вакансия 8');
  });
});
