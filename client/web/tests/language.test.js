// Язык приложения, пришедший от моста: по нему сортируются имена.

import { describe, expect, it } from 'vitest';

import { holdLocale } from '../state/language.js';
import { pickNames } from '../state/vacancy_filter.js';

describe('язык приложения', () => {
  it('имена сортируются по принятому языку, а не по своему', () => {
    // По-шведски «ä» — отдельная буква после «z», в общем порядке — рядом с «a».
    holdLocale('sv');

    expect(pickNames(['ä', 'z'], '')).toEqual(['z', 'ä']);
  });

  it('без принятого языка сортировка падает, а не берёт язык системы', () => {
    holdLocale(undefined);

    expect(() => pickNames(['б', 'а'], '')).toThrow('Язык приложения ещё не получен');
  });
});
