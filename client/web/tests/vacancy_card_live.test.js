// @vitest-environment jsdom
//
// Карточка вакансии, которой сменили номер записи.
//
// Панель одна на весь список: выбор другой строки не заводит компонент заново,
// а меняет ему одно свойство. Не назови эффект этот номер своей зависимостью —
// на экране осталась бы прежняя вакансия, и человек правил бы статус не той.

import { afterEach, describe, expect, it } from 'vitest';

import { settled } from './settled.js';
import { mountVacancyCard } from './vacancy_card_mount.js';
import { vacancyDetail } from './vacancy_detail.js';

let card = null;

afterEach(() => {
  card?.remove();
  card = null;
});

function screen(extra = {}) {
  card = mountVacancyCard((method, payload) => ({ vacancy: vacancyDetail(payload, extra) }));
  return { asked: card.asked, change: card.change, text: () => card.host.textContent };
}

describe('живая карточка вакансии', () => {
  it('перечитывается, когда открыли другую вакансию', async () => {
    const { asked, change, text } = screen();
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
    const { text } = screen({
      salary: '🎯 ЗП: действительно готовы обсудить ваши пожелания',
      salary_min: 500000,
      salary_max: 700000,
      salary_currency: '֏',
    });

    await settled();

    expect(text()).toContain('от 500000 до 700000 ֏');
    expect(text()).not.toContain('готовы обсудить');
  });

  it('нажатие на название кладёт его в буфер обмена и говорит об этом', async () => {
    const copied = [];
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: async (text) => copied.push(text) },
      configurable: true,
    });
    screen({ title: 'Повар в бистро' });
    await settled();

    card.host.querySelector('.det-title').click();
    await settled();

    expect(copied).toEqual(['Повар в бистро']);
    expect(card.said).toContain('Название скопировано');
  });
});

