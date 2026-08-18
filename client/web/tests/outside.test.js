// Следствия сторожа «нажали мимо».
//
// Документа в прогоне нет — проверки идут в node, — поэтому он подставляется:
// предмет здесь не браузер, а правило, по которому окошко решает закрыться.

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { closeOnClickAway } from '$state/outside.js';

let listeners;

beforeEach(() => {
  listeners = [];
  globalThis.document = {
    addEventListener: (kind, fn) => listeners.push([kind, fn]),
    removeEventListener: (kind, fn) => {
      listeners = listeners.filter(([k, f]) => k !== kind || f !== fn);
    },
  };
});

afterEach(() => {
  delete globalThis.document;
});

/** Узел, считающий своими только перечисленные цели. */
function node(...own) {
  return { contains: (target) => own.includes(target) };
}

function press(target) {
  for (const [, fn] of listeners) fn({ target });
}

describe('нажатие мимо', () => {
  it('закрывает окошко', () => {
    let closed = false;
    closeOnClickAway(() => node('своё'), () => (closed = true));

    press('чужое');

    expect(closed).toBe(true);
  });

  it('нажатие внутрь окошка не закрывает', () => {
    // Иначе выбор из списка закрывал бы список раньше, чем сработает выбор.
    let closed = false;
    closeOnClickAway(() => node('своё'), () => (closed = true));

    press('своё');

    expect(closed).toBe(false);
  });

  it('кнопка, открывшая окошко, своей и считается', () => {
    // Она панели не принадлежит, а живёт с ней в одной обёртке. Считай своим
    // узлом панель — и щелчок, открывший окошко, дошёл бы до документа и
    // закрыл его обратно: снаружи это не нажимающаяся кнопка.
    let closed = false;
    closeOnClickAway(() => node('панель', 'кнопка'), () => (closed = true));

    press('кнопка');

    expect(closed).toBe(false);
  });

  it('до появления узла не закрывает ничего', () => {
    // Разметка привязывает узел после первого показа, и до тех пор окошка на
    // экране нет вовсе.
    let closed = false;
    closeOnClickAway(() => null, () => (closed = true));

    press('что угодно');

    expect(closed).toBe(false);
  });

  it('снятие убирает сторожа', () => {
    // Иначе на каждое открытие копился бы ещё один, и закрытое окошко
    // продолжало бы отзываться на нажатия.
    let closed = false;
    const off = closeOnClickAway(() => node('своё'), () => (closed = true));

    off();
    press('чужое');

    expect(listeners).toEqual([]);
    expect(closed).toBe(false);
  });
});
