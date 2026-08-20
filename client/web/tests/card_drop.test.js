// Следствия сноса записи из правой панели: что человек слышит и что видит
// после нажатия.

import { describe, expect, it } from 'vitest';

import { cardDrop } from '../state/card_drop.js';

/** Панель, записывающая всё, что с ней сделали, — в том порядке, в каком делали. */
function panel(answer) {
  const trail = [];
  const drop = cardDrop({
    ask: () => Promise.resolve(answer),
    method: 'channels.delete',
    note: 'Канал удалён',
    say: (text) => trail.push(`сказано: ${text}`),
    onchanged: () => trail.push('список перечитан'),
    onclose: () => trail.push('панель закрыта'),
  });
  return { drop, trail };
}

describe('снос записи из карточки', () => {
  it('человеку говорят о сносе прежде, чем панель уходит из-под него', async () => {
    // Без слова человек не знает, снесена ли запись или панель просто
    // закрылась; сказанное вслед закрытой панели он читает уже мимо неё.
    // Список перечитывают до закрытия: закройся панель раньше, снесённая
    // строка осталась бы под ней до следующего чтения.
    const one = panel({ deleted: true });

    await one.drop(7);

    expect(one.trail).toEqual(['сказано: Канал удалён', 'список перечитан', 'панель закрыта']);
  });

  it('отказ моста не закрывает панель и молчит', async () => {
    // Плашку об отказе человек уже увидел; закрытая панель поверх неё читалась
    // бы как «снесено», а снесено ничего не было.
    const one = panel(null);

    await one.drop(7);

    expect(one.trail).toEqual([]);
  });

  it('мосту уходит номер записи', async () => {
    const asked = [];
    const drop = cardDrop({
      ask: (method, id) => {
        asked.push([method, id]);
        return Promise.resolve({ deleted: true });
      },
      method: 'vacancies.delete',
      note: 'Вакансия удалена',
      say: () => {},
      onchanged: () => {},
      onclose: () => {},
    });

    await drop({ vacancy_id: 3 });

    expect(asked).toEqual([['vacancies.delete', { vacancy_id: 3 }]]);
  });
});
