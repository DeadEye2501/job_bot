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
import { vacancyDetail } from './vacancy_detail.js';

let mounted = null;
let host = null;

afterEach(() => {
  if (mounted) flushSync(() => unmount(mounted));
  host?.remove();
  mounted = null;
  host = null;
});

function screen(vacancyId, extra = {}) {
  const asked = [];
  const [props, change] = livingProps({
    ask: async (method, payload) => {
      asked.push([method, payload]);
      return { vacancy: vacancyDetail(payload, extra) };
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

  it('зарплату показывает пилюлей из разобранных чисел, а не строкой поста', async () => {
    // Наставление разбора велит модели брать зарплату дословно, и в поле
    // ложится написанное автором: «🎯 ЗП: действительно готовы обсудить ваши
    // пожелания». В пилюле такому не место — она показывает только числа.
    const { text } = screen(7, {
      salary: '🎯 ЗП: действительно готовы обсудить ваши пожелания',
      salary_min: 500000,
      salary_max: 700000,
      salary_currency: '֏',
    });

    await settled();

    expect(text()).toContain('от 500000 до 700000 ֏');
    expect(text()).not.toContain('готовы обсудить');
  });
});
