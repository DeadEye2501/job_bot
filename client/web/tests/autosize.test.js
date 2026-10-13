// Следствия подгона высоты поля под набранное.
//
// Разметки в прогоне нет — проверки идут в node, — поэтому поле подставляется:
// предмет здесь не браузер, а порядок, в котором высоту меряют и ставят.

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

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
    dataset: {},
    offsetHeight: 0,
    clientHeight: 0,
    addEventListener: (kind, fn) => heard.set(kind, fn),
    removeEventListener: (kind, fn) => heard.get(kind) === fn && heard.delete(kind),
    style: {
      set height(value) {
        trail.push(value);
      },
      get height() {
        return trail.at(-1);
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

describe('поле с рамкой', () => {
  it('рамка прибавляется к высоте текста — иначе текст не влезает, и сбоку встаёт прокрутка', () => {
    const one = field(64);
    one.offsetHeight = 42;
    one.clientHeight = 40;

    fitHeight(one);

    expect(one.trail.at(-1)).toBe('66px');
  });
});

describe('поле с пределом строк', () => {
  // Строка — 20px, поля сверху и снизу по 6px: предел в две строки — 52px.
  // Вида поля в node нет, и его отдаёт подставной замер браузера.
  beforeEach(() => {
    globalThis.getComputedStyle = () => ({ lineHeight: '20px', paddingTop: '6px', paddingBottom: '6px' });
  });
  afterEach(() => {
    delete globalThis.getComputedStyle;
  });

  function limited(fits) {
    const one = field(fits);
    one.dataset.lines = '2';
    return one;
  }

  it('длинный текст — не выше предела', () => {
    const one = limited(500);

    fitHeight(one);

    expect(one.trail.at(-1)).toBe('52px');
  });

  it('высота строки «normal» считается от размера шрифта', () => {
    globalThis.getComputedStyle = () => ({
      lineHeight: 'normal', fontSize: '10px', paddingTop: '6px', paddingBottom: '6px',
    });
    const one = limited(500);

    fitHeight(one);

    expect(one.trail.at(-1)).toBe('36px');
  });

  it('короткий текст — по себе, предел его не растягивает', () => {
    const one = limited(30);

    fitHeight(one);

    expect(one.trail.at(-1)).toBe('30px');
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
    const before = one.trail.length;

    one.heard.get('input')();

    expect(one.trail.slice(before)).toEqual(['auto', '64px']);
  });

  it('растянутое рукой больше не подгоняет — ни на набор, ни на смену текста', async () => {
    // Человек растянул поле, чтобы видеть больше, и печатает дальше: прыжок
    // обратно отнял бы то, ради чего он тянул. Заново поле подгонится, когда
    // его заведут снова — при новом входе на вкладку.
    const one = field(64);
    const grown = growing(one);
    one.style.height = '300px';

    one.heard.get('input')();
    await grown.update();

    expect(one.trail.at(-1)).toBe('300px');
  });

  it('уходя, снимает за собой слушателя', () => {
    // Полей этих много и живут они недолго — строка списка, строка ленты, — и
    // оставленный слушатель держал бы за собой всё поле целиком.
    const one = field(64);

    growing(one).destroy();

    expect(one.heard.has('input')).toBe(false);
  });
});
