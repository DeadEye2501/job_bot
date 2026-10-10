// Слова, согласованные с числами.

import { describe, expect, it } from 'vitest';

import { vacancyCount } from '../state/words.js';

describe('счёт вакансий', () => {
  it('число и слово согласованы', () => {
    expect(vacancyCount(1)).toBe('1 вакансия');
    expect(vacancyCount(3)).toBe('3 вакансии');
    expect(vacancyCount(12)).toBe('12 вакансий');
  });
});
