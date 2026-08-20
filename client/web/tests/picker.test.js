// Следствия окна выбора: когда выбранным можно связывать.

import { describe, expect, it } from 'vitest';

import { linkReady } from '../state/picker.js';

describe('запор кнопки «Связать»', () => {
  it('пока никого не выбрали, связывать нечем', () => {
    expect(linkReady({ current: 4, chosen: null })).toBe(false);
  });

  it('выбор того же, кто уже привязан, кнопку не отпирает', () => {
    // Иначе нажатие переписывает привязку тем же значением и пишет в журнал
    // перемену, которой не было.
    expect(linkReady({ current: 4, chosen: 4 })).toBe(false);
  });

  it('выбор другого отпирает кнопку', () => {
    expect(linkReady({ current: 4, chosen: 9 })).toBe(true);
  });

  it('выбор при пустой привязке отпирает кнопку', () => {
    expect(linkReady({ current: null, chosen: 9 })).toBe(true);
  });
});
