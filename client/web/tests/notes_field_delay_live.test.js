// @vitest-environment jsdom
//
// Своя пауза поля заметки.
//
// Пауза приходила доводом от каждой карточки, и три её объявления разъехались:
// у человека и компании 600, у вакансии 800 — без записанной причины, а
// пояснения при этом друг другу противоречили. Поле при этом одно и то же, и
// про соседнее число того же компонента сказано прямо: предел длины — один на
// все три места.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import NotesField from '../components/NotesField.svelte';

afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

describe('живое поле заметки', () => {
  it('ждёт свою паузу, а не ту, что подадут снаружи', async () => {
    vi.useFakeTimers();
    const written = [];
    const shown = render(NotesField, {
      props: {
        value: '',
        placeholder: 'заметка',
        owner: 7,
        save: async (owner, typed) => {
          written.push({ owner, typed });
          return typed;
        },
      },
    });

    const field = shown.getByRole('textbox');
    field.value = 'позвонить в пятницу';
    field.dispatchEvent(new Event('input', { bubbles: true }));

    // Пауза считается от последнего знака и она своя: подай её снаружи или не
    // подай вовсе — поле обязано ждать одинаково. Пропущенный довод давал
    // нулевую паузу, то есть вопрос мосту на каждую букву.
    await vi.advanceTimersByTimeAsync(100);
    expect(written).toEqual([]);

    await vi.advanceTimersByTimeAsync(2000);

    expect(written).toEqual([{ owner: 7, typed: 'позвонить в пятницу' }]);
  });
});
