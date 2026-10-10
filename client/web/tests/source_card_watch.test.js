// Заход на карточку источника — канала или агрегатора: сброс прежнего, чтение
// и слежение за вакансиями, которые он приносит.

import { describe, expect, it } from 'vitest';

import { watchSourceCard } from '$state/source_card.svelte.js';

import { listening } from './bridge_stub.js';

const ALIVE = { entered: (read) => (read(), () => {}) };

describe('заход на карточку источника', () => {
  it('сперва убирает показанное прежним, потом читает новый', () => {
    const trail = [];
    watchSourceCard(listening(), ALIVE, 7, {
      forget: () => trail.push('сброс'),
      read: (id) => trail.push(`чтение ${id}`),
    });
    expect(trail).toEqual(['сброс', 'чтение 7']);
  });

  it('весть о смене вакансий перечитывает открытый источник', () => {
    const events = listening();
    const read = [];
    watchSourceCard(events, ALIVE, 7, { forget: () => {}, read: (id) => read.push(id) });

    events.fire('vacancies_list_changed');

    expect(read).toEqual([7, 7]);
  });

  it('снятие отписывает от вестей', () => {
    const events = listening();
    const off = watchSourceCard(events, ALIVE, 7, { forget: () => {}, read: () => {} });

    off();

    expect(events.heard('vacancies_list_changed')).toBe(false);
  });
});
