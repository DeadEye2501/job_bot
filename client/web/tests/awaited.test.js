// Ожидание своей вести: кнопка пустила работу и ждёт итог по своей метке.

import { afterEach, describe, expect, it } from 'vitest';

import { awaited } from '$state/awaited.svelte.js';

import { awaitingNews } from './bridge_stub.js';

let deaf = () => {};
afterEach(() => deaf());

/** Подписать учёт на подставные вести; ответ — доставка итога работы. */
function news() {
  const heard = awaitingNews();
  deaf = heard.deaf;
  return heard.finished;
}

describe('ожидание своей вести', () => {
  it('ждущий получает только свою весть, и ожидание с ней гаснет', () => {
    const finished = news();
    const got = [];
    awaited.start('parse_cv', (payload) => got.push(payload));

    finished({ action: 'rerun', message: 'чужое' });
    expect(awaited.pending('parse_cv')).toBe(true);

    finished({ action: 'parse_cv', message: 'своё' });
    expect(got).toEqual([{ action: 'parse_cv', message: 'своё' }]);
    expect(awaited.pending('parse_cv')).toBe(false);
  });

  it('весть без ожидания никого не зовёт', () => {
    const finished = news();
    const got = [];
    awaited.start('parse_cv', (payload) => got.push(payload));
    finished({ action: 'parse_cv' });

    finished({ action: 'parse_cv' });

    expect(got).toHaveLength(1);
  });

  it('отказанный до пуска зов снимает ожидание', () => {
    news();
    awaited.start('create_by_hand', () => {});

    awaited.cancel('create_by_hand');

    expect(awaited.pending('create_by_hand')).toBe(false);
  });

  it('свежая подписка начинает без ожиданий: прошлое окно своих вестей не дождётся', () => {
    awaited.start('parse_cv', () => {});

    news();

    expect(awaited.pending('parse_cv')).toBe(false);
  });
});
