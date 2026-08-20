// Следствия счёта попыток: какой ответ экран принимает, а какой отбрасывает.
//
// Мост тут ни при чём: счётчик о нём не знает, и предмет его — только порядок
// запросов, обгоняющих друг друга.

import { describe, expect, it } from 'vitest';

import { attempts } from '../state/attempts.js';

describe('счёт попыток', () => {
  it('ответ на устаревшую попытку отбрасывается', () => {
    // Человек правит поиск быстрее, чем отвечает база. Приди ответ на прежний
    // запрос вторым, список показал бы результат позапрошлого набранного.
    const numbers = attempts();
    const first = numbers.next();
    const second = numbers.next();

    expect(numbers.stale(first)).toBe(true);
    expect(numbers.stale(second)).toBe(false);
  });

  it('свой счёт у каждого места, а не один на страницу', () => {
    // Общий счётчик отбрасывал бы ответы соседнего экрана: поиск в контактах
    // гасил бы ответ прокрутки в вакансиях.
    const here = attempts();
    const there = attempts();
    const mine = here.next();
    there.next();

    expect(here.stale(mine)).toBe(false);
  });
});
