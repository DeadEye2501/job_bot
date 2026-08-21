// @vitest-environment jsdom
//
// Правимая строка ленты на поднятом компоненте.
//
// Разметку ленты не сторожил никто: проверки состояния (`vacancy_card.test.js`)
// считают строки, а рисование их не касается. Из-за этого зов распорядителя,
// потерявшего своё объявление, доехал до окна нетронутым — компилятор считает
// свободное имя глобальным и молчит, а собранный код падает `ReferenceError` на
// первой же строке, которую человек правил руками.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import VacancyTimeline from '../components/VacancyTimeline.svelte';

afterEach(cleanup);

describe('живая лента вакансии', () => {
  it('даёт править свою строку и растягивает поле под набранное', () => {
    const row = {
      key: 'h1',
      kind: 'history',
      status: 'Applied',
      label: 'Applied:',
      text: 'откликнулся сам',
      when: '2026-08-20T10:00:00+03:00',
      at: Date.parse('2026-08-20T10:00:00+03:00'),
      historyId: 1,
      editable: true,
    };

    const shown = render(VacancyTimeline, {
      props: { rows: [row], vacancyId: 7, onsave: async () => true },
    });

    const field = shown.getByRole('textbox');
    expect(field.value).toBe('откликнулся сам');
    // Высота поставлена при заведении поля, а не при первом наборе: строка с
    // длинным пояснением показывала бы только первую свою строчку до тех пор,
    // пока в неё не ткнут.
    expect(field.style.height).not.toBe('');
  });
});
