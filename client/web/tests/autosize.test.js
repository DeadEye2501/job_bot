// Следствия подгона высоты поля под набранное.
//
// Разметки в прогоне нет — проверки идут в node, — поэтому поле подставляется:
// предмет здесь не браузер, а порядок, в котором высоту меряют и ставят.

import { describe, expect, it } from 'vitest';

import { fitHeight, growing } from '../state/autosize.js';

/** Поле, помнящее всё, что ему ставили в высоту.
 *
 * Измеренная высота отвечает по последнему поставленному: настоящее поле
 * меряет содержимое ровно так — сжатое до `auto` показывает свой текст, а
 * растянутое прежним значением показывает это самое прежнее.
 */
function field(fits) {
  const trail = [];
  const heard = new Map();
  return {
    trail,
    heard,
    addEventListener: (kind, fn) => heard.set(kind, fn),
    removeEventListener: (kind, fn) => heard.get(kind) === fn && heard.delete(kind),
    style: {
      set height(value) {
        trail.push(value);
      },
    },
    get scrollHeight() {
      return trail.at(-1) === 'auto' ? fits : 999;
    },
  };
}

describe('высота поля по набранному', () => {
  it('поле становится высотой в свой текст', () => {
    const one = field(64);

    fitHeight(one);

    expect(one.trail.at(-1)).toBe('64px');
  });

  it('перед замером поле сжимается', () => {
    // Иначе меряется прежняя высота: растянутое поле показывает её и после
    // того, как текст из него убрали, — стёртый абзац оставил бы дыру.
    const one = field(64);

    fitHeight(one);

    expect(one.trail).toEqual(['auto', '64px']);
  });
});

describe('поле, растущее пока живёт', () => {
  it('подгоняет высоту сразу, не дожидаясь первого знака', () => {
    // Иначе строка с длинным пояснением показывала бы первую свою строчку до
    // тех пор, пока в неё не ткнут.
    const one = field(64);

    growing(one);

    expect(one.trail).toEqual(['auto', '64px']);
  });

  it('подгоняет её на каждый набор', () => {
    const one = field(64);
    growing(one);
    one.trail.length = 0;

    one.heard.get('input')();

    expect(one.trail).toEqual(['auto', '64px']);
  });

  it('уходя, снимает за собой слушателя', () => {
    // Полей этих много и живут они недолго — строка списка, строка ленты, — и
    // оставленный слушатель держал бы за собой всё поле целиком.
    const one = field(64);

    growing(one).destroy();

    expect(one.heard.has('input')).toBe(false);
  });
});
