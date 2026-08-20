// Следствия действия, после которого карточки не остаётся: что человек слышит,
// что видит и что узнаёт зовущий.

import { describe, expect, it } from 'vitest';

import { cardFinish } from '../state/card_finish.js';

/** Панель, записывающая всё, что с ней сделали, — в том порядке, в каком делали. */
function panel(answer) {
  const trail = [];
  const finish = cardFinish({
    ask: () => Promise.resolve(answer),
    method: 'channels.delete',
    note: 'Канал удалён',
    say: (text) => trail.push(`сказано: ${text}`),
    onchanged: () => trail.push('список перечитан'),
    onclose: () => trail.push('панель закрыта'),
  });
  return { finish, trail };
}

describe('действие, кончающее карточку', () => {
  it('человеку говорят о нём прежде, чем панель уходит из-под него', async () => {
    // Без слова человек не знает, снесена ли запись или панель просто
    // закрылась; сказанное вслед закрытой панели он читает уже мимо неё.
    // Список перечитывают до закрытия: закройся панель раньше, снесённая
    // строка осталась бы под ней до следующего чтения.
    const one = panel({ deleted: true });

    await one.finish(7);

    expect(one.trail).toEqual(['сказано: Канал удалён', 'список перечитан', 'панель закрыта']);
  });

  it('отказ моста не закрывает панель и молчит', async () => {
    // Плашку об отказе человек уже увидел; закрытая панель поверх неё читалась
    // бы как «снесено», а снесено ничего не было.
    const one = panel(null);

    await one.finish(7);

    expect(one.trail).toEqual([]);
  });

  it('зовущему сказано, случилось ли это', async () => {
    // По этому ответу закрывают своё окно те, у кого оно есть: слияние гасит
    // окно выбора, а по отказу оставляет его открытым — выбранное ещё нужно.
    expect(await panel({ merged: true }).finish(7)).toBe(true);
    expect(await panel(null).finish(7)).toBe(false);
  });

  it('мосту уходит названная нагрузка', async () => {
    const asked = [];
    const finish = cardFinish({
      ask: (method, payload) => {
        asked.push([method, payload]);
        return Promise.resolve({ merged: true });
      },
      method: 'hr.merge',
      note: 'Карточки слиты',
      say: () => {},
      onchanged: () => {},
      onclose: () => {},
    });

    await finish({ absorbed_id: 3, survivor_id: 9 });

    expect(asked).toEqual([['hr.merge', { absorbed_id: 3, survivor_id: 9 }]]);
  });
});
