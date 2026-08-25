// @vitest-environment jsdom
//
// Подсказка поля, которым называют чужую карточку: выпадает ли она вовсе.
//
// Поле общее с настройками, а принимает набранное по-разному: здесь его
// принимают явно (`asked`), там — уходом из поля. Проверяется тот довод, при
// котором принятое заводит запись.
//
// Проверка живая, а не по чистой функции: список падает из состояния самого
// поля — фокус открывает панель, набранное её просеивает, — и просеивание,
// проверенное отдельно, ничего не говорит о том, дошло ли оно до экрана.

import { cleanup, fireEvent, render, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import SuggestInput from '../components/SuggestInput.svelte';

afterEach(cleanup);

const HRS = ['Alexandra', 'Анна', 'Ирина'];

function field(props = {}) {
  const shown = render(SuggestInput, {
    props: {
      value: '',
      options: HRS,
      placeholder: 'HR',
      asked: true,
      onsave: () => {},
      ...props,
    },
  });
  return { shown, input: within(shown.container).getByPlaceholderText('HR') };
}

describe('живое поле с подсказкой', () => {
  it('на фокусе показывает все заведённые имена', async () => {
    // Человек открывает поле, ещё ничего не набрав: до подсказки он не знает,
    // заведён ли нужный, и пустая панель гонит его заводить второго такого же.
    const { shown, input } = field();

    await fireEvent.focus(input);

    for (const name of HRS) {
      expect(within(shown.container).getByText(name)).toBeTruthy();
    }
  });

  it('набранное просеивает подсказку, не пряча её целиком', async () => {
    const { shown, input } = field();

    await fireEvent.focus(input);
    await fireEvent.input(input, { target: { value: 'ан' } });

    expect(within(shown.container).getByText('Анна')).toBeTruthy();
    expect(within(shown.container).queryByText('Ирина')).toBe(null);
  });

  it('тёзки в перечне подсказку не роняют', async () => {
    // Имя человека уникальным не бывает: у одного собеседника их трое с одним
    // и тем же. Пункты, перечисленные с ключом по значению, на втором тёзке
    // роняют отрисовку — и панель не появляется вовсе, молча.
    const { shown, input } = field({ options: ['Ирина', 'Ирина', 'Ирина', 'Yana'] });

    await fireEvent.focus(input);

    expect(within(shown.container).getAllByText('Ирина')).toHaveLength(3);
  });

  it('над пустым полем принимать нечего', async () => {
    // Стёртое имя — не имя: галочка над пустым полем обещает завести карточку
    // без названия, а такую не найти потом ничем.
    const { shown, input } = field({ value: 'Ирина · @ira_recr' });

    await fireEvent.focus(input);
    await fireEvent.input(input, { target: { value: '  ' } });

    expect(within(shown.container).queryByTitle('Принять имя')).toBe(null);
  });

  it('стёртое поле не помечает в подсказке прежнего выбранного', async () => {
    // Пометка говорит «вот это сейчас в поле». Оставь её на прежнем имени
    // после стирания — человек читает её как «выбран он», хотя поле пустое.
    const { shown, input } = field({ value: 'Анна' });

    await fireEvent.focus(input);
    await fireEvent.input(input, { target: { value: '' } });

    const marked = shown.container.querySelectorAll('.cdd-option.active');
    expect(marked).toHaveLength(0);
  });
});
