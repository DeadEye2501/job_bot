// Ник записи в Telegram: как он подписан и чем подписано его отсутствие.

import { describe, expect, it } from 'vitest';

import { atHandle, handleName } from '../state/telegram.js';

describe('ник в Telegram', () => {
  it('пишется с собакой, а без ника пусто — запасное слово у места показа', () => {
    expect(atHandle('ivan')).toBe('@ivan');
    expect(atHandle('')).toBe('');
    expect(atHandle(null)).toBe('');
  });

  it('в списке отсутствие ника названо прямо', () => {
    expect(handleName('ivan')).toBe('@ivan');
    expect(handleName(null)).toBe('без ника');
  });
});
