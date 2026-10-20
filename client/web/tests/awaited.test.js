// Ожидание своей вести: кнопка пустила работу и ждёт итог по своей метке.

import { afterEach, describe, expect, it } from 'vitest';

import { awaited, hearAwaited } from '$state/awaited.svelte.js';

/** Слушатель вестей, которым тест сам доставляет вести. */
function news() {
  const heard = new Map();
  return {
    events: {
      on(kind, hear) {
        heard.set(kind, hear);
        return () => heard.delete(kind);
      },
    },
    finished: (payload) => heard.get('action_finished')?.(payload),
  };
}

let deaf = () => {};
afterEach(() => deaf());

describe('ожидание своей вести', () => {
  it('ждущий получает только свою весть, и ожидание с ней гаснет', () => {
    const { events, finished } = news();
    deaf = hearAwaited(events);
    const got = [];
    awaited.start('parse_cv', (payload) => got.push(payload));

    finished({ action: 'rerun', message: 'чужое' });
    expect(awaited.pending('parse_cv')).toBe(true);

    finished({ action: 'parse_cv', message: 'своё' });
    expect(got).toEqual([{ action: 'parse_cv', message: 'своё' }]);
    expect(awaited.pending('parse_cv')).toBe(false);
  });

  it('весть без ожидания никого не зовёт', () => {
    const { events, finished } = news();
    deaf = hearAwaited(events);
    const got = [];
    awaited.start('parse_cv', (payload) => got.push(payload));
    finished({ action: 'parse_cv' });

    finished({ action: 'parse_cv' });

    expect(got).toHaveLength(1);
  });

  it('отказанный до пуска зов снимает ожидание', () => {
    const { events } = news();
    deaf = hearAwaited(events);
    awaited.start('create_from_text', () => {});

    awaited.cancel('create_from_text');

    expect(awaited.pending('create_from_text')).toBe(false);
  });

  it('свежая подписка начинает без ожиданий: прошлое окно своих вестей не дождётся', () => {
    awaited.start('parse_cv', () => {});
    const { events } = news();

    deaf = hearAwaited(events);

    expect(awaited.pending('parse_cv')).toBe(false);
  });
});
