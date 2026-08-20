// Следствия отметки «открой эту запись», пришедшей со стороны: что вкладка
// открывает и почему отметка не переживает открытия.

import { describe, expect, it } from 'vitest';

import { takeOpened } from '../state/open_mark.js';

describe('отметка «открой эту запись»', () => {
  it('названная запись открывается', async () => {
    // Так приходят из статистики и из карточки вакансии: человек нажал строку
    // и ждёт открытой карточки, а не просто открытой вкладки.
    let shown = null;

    takeOpened({ id: 12 }, (id) => (shown = id), () => {});

    expect(shown).toBe(12);
  });

  it('отметка гасится сразу после открытия', async () => {
    // Вкладку открывают и просто так: непогашенная отметка открыла бы заново
    // карточку, которую человек уже закрыл.
    let burnt = false;

    takeOpened({ id: 12 }, () => {}, () => (burnt = true));

    expect(burnt).toBe(true);
  });

  it('без отметки не открывают ничего', async () => {
    let touched = false;

    takeOpened(null, () => (touched = true), () => (touched = true));

    expect(touched).toBe(false);
  });
});
