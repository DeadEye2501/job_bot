// Следствия зова моста, отбивающего устаревший ответ: что доезжает до экрана,
// а что не кладётся никуда.

import { describe, expect, it } from 'vitest';

import { freshAnswer } from '../state/fresh.js';
import { held } from './bridge_stub.js';

describe('свежий ответ моста', () => {
  it('единственный ответ доезжает до экрана', async () => {
    const fresh = freshAnswer(() => true);

    expect(await fresh(() => Promise.resolve({ rows: [1] }))).toEqual({ rows: [1] });
  });

  it('отказ моста класть нечего', async () => {
    // Мост отвечает пустотой на любую свою беду; экран по ней не перерисовывают,
    // иначе список схлопывался бы на каждом обрыве.
    const fresh = freshAnswer(() => true);

    expect(await fresh(() => Promise.resolve(null))).toBe(null);
  });

  it('обогнанный ответ не кладётся', async () => {
    // Человек набирает поиск посимвольно, ответы возвращаются вразнобой: лёгший
    // поверх свежего старый показал бы строки, которых он уже не ищет.
    const fresh = freshAnswer(() => true);
    const first = held('старое');

    const early = fresh(() => first.promise);
    const late = await fresh(() => Promise.resolve('свежее'));
    first.give();

    expect(await early).toBe(null);
    expect(late).toBe('свежее');
  });

  it('ответ в закрытый экран не кладётся', async () => {
    // Ответы доезжают и после ухода с экрана, а положенное в снесённое
    // состояние всплывает при следующем заходе поверх свежего.
    let live = true;
    const fresh = freshAnswer(() => live);
    const answer = held('ответ');

    const going = fresh(() => answer.promise);
    live = false;
    answer.give();

    expect(await going).toBe(null);
  });

  it('у каждого зова свой счёт', async () => {
    // Общий счёт на экран объявлял бы устаревшим ответ соседнего вопроса:
    // здоровье, непрочитанное и режим спрашивают вперемешку.
    const one = freshAnswer(() => true);
    const other = freshAnswer(() => true);
    const slow = held('первый');

    const early = one(() => slow.promise);
    await other(() => Promise.resolve('второй'));
    slow.give();

    expect(await early).toBe('первый');
  });
});
