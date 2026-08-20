// Следствия правки поля карточки: что человек видит после ответа моста и что
// узнаёт о правке список.

import { describe, expect, it } from 'vitest';

import { cardSave } from '../state/card_save.js';

/** Карточка, записывающая всё, что с ней сделали. */
function card(answer) {
  const trail = [];
  const save = cardSave({
    ask: (method, payload) => {
      trail.push(`спрошено: ${method} ${JSON.stringify(payload)}`);
      return Promise.resolve(answer);
    },
    // Перечитывание отложено нарочно: сними кто-нибудь `await` перед ним, и
    // список узнал бы о правке раньше самой карточки — а он-то и решает, что
    // показывать.
    reread: async () => {
      await Promise.resolve();
      trail.push('карточка перечитана');
    },
    method: 'hr.update',
    onchanged: () => trail.push('список перечитан'),
  });
  return { save, trail };
}

describe('правка поля карточки', () => {
  it('после записи карточку перечитывают', async () => {
    // Поля правятся на месте, и показанным считается только то, что легло в
    // базу: мост правит значение по дороге — обрезает края, сводит регистр.
    const one = card({ updated: true });

    await one.save({ hr_id: 3, name: 'Аня' });

    expect(one.trail).toEqual([
      'спрошено: hr.update {"hr_id":3,"name":"Аня"}',
      'карточка перечитана',
      'список перечитан',
    ]);
  });

  it('отказ тоже перечитывает карточку, но списку не говорит', async () => {
    // Отклонённое мостом значение осталось бы на экране: человек читал бы
    // своё, а в базе лежало бы прежнее. Списку при этом говорить нечего —
    // ничего не изменилось.
    const one = card(null);

    await one.save({ hr_id: 3, telegram_username: 'не ник' });

    expect(one.trail).toEqual([
      'спрошено: hr.update {"hr_id":3,"telegram_username":"не ник"}',
      'карточка перечитана',
    ]);
  });
});
