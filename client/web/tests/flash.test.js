// Следствие отметки «записано»: загорается и гаснет сама.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flashing } from '../state/flash.js';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('отметка «записано»', () => {
  it('гаснет сама', () => {
    // Оставленная гореть, она встретила бы соседнюю строку зелёной рамкой на
    // нетронутом поле.
    const seen = [];
    const mark = flashing((on) => seen.push(on));
    mark();
    vi.advanceTimersByTime(1000);
    expect(seen).toEqual([true, false]);
  });

  it('вторая запись подряд продлевает свечение, а не гасит его на полпути', () => {
    // Иначе быстрая правка двух полей оставляла бы рамку гореть по времени
    // первой, и вторая запись выглядела бы незаписанной.
    const seen = [];
    const mark = flashing((on) => seen.push(on));
    mark();
    vi.advanceTimersByTime(300);
    mark();
    vi.advanceTimersByTime(300);
    expect(seen).toEqual([true, true]);
    vi.advanceTimersByTime(1000);
    expect(seen).toEqual([true, true, false]);
  });
});
