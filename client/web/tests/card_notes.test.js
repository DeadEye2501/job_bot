// Следствия записи заметки в карточке: что возвращается полю и когда о правке
// узнаёт список.

import { describe, expect, it } from 'vitest';

import { cardNotes } from '../state/card_notes.js';

import { relisting, tracing } from './bridge_stub.js';

/** Карточка с заметкой, записывающая всё, что с ней сделали. */
function card(answer, live = true) {
  const trail = [];
  const saveNotes = cardNotes({
    ask: tracing(trail, answer),
    method: 'hr.update',
    payload: (id, text) => ({ hr_id: id, notes: text }),
    alive: () => live,
    onchanged: relisting(trail),
  });
  return { saveNotes, trail };
}

describe('запись заметки', () => {
  it('легшим считается набранное, а не пришедшее из базы', async () => {
    // Человек мог набрать ещё, пока летел вопрос: пришедшее из базы стёрло бы
    // это. Самой заметки в ответе нет вовсе — зов называет только поправленное.
    const one = card({ updated: true });

    expect(await one.saveNotes(3, 'позвонить в пятницу')).toBe('позвонить в пятницу');
    expect(one.trail).toEqual([
      'спрошено: hr.update {"hr_id":3,"notes":"позвонить в пятницу"}',
      'список перечитан',
    ]);
  });

  it('отказ моста не считается записью', async () => {
    // Поле по этому ответу оставляет набранное несохранённым: следующая
    // попытка уедет тем же текстом.
    const one = card(null);

    expect(await one.saveNotes(3, 'позвонить')).toBe(null);
    expect(one.trail).not.toContain('список перечитан');
  });

  it('ответ, доехавший в закрытую карточку, никуда не кладётся', async () => {
    // Панель закрывают, не дожидаясь записи: сказанное закрытой карточке
    // всплыло бы над следующей, открытой на её месте.
    const one = card({ updated: true }, false);

    expect(await one.saveNotes(3, 'позвонить')).toBe(null);
    expect(one.trail).not.toContain('список перечитан');
  });
});
