// Следствия клавиш в модальном окне: чем закрывают и чем подтверждают.

import { describe, expect, it } from 'vitest';

import { modalKey, modalPress, opened, saveKey } from '../state/keys.js';

const ESCAPE = { key: 'Escape', target: { tagName: 'BODY' } };

describe('клавиши модального окна', () => {
  it('Escape закрывает', () => {
    // Без этого окно закрывается только мышью: клавиатурой из него не выйти.
    expect(modalKey({ key: 'Escape', target: { tagName: 'INPUT' } })).toBe('close');
  });

  it('Enter подтверждает из однострочного поля', () => {
    expect(modalKey({ key: 'Enter', target: { tagName: 'INPUT' } })).toBe('confirm');
  });

  it('Enter в многострочном поле переносит строку, а не подтверждает', () => {
    // Иначе заметку в два абзаца не набрать: первый же перевод строки отправит.
    expect(modalKey({ key: 'Enter', target: { tagName: 'TEXTAREA' } })).toBe(null);
  });

  it('прочие клавиши ничего не значат', () => {
    expect(modalKey({ key: 'a', target: { tagName: 'INPUT' } })).toBe(null);
  });
});

describe('стопка открытых окон', () => {
  it('нажатие достаётся верхнему окну, а не всей стопке', () => {
    // Окна встают друг на друга: слияние открывает подборщик поверх карточки, а
    // подтверждение — поверх подборщика. Достанься Escape всем, один нажим
    // закрыл бы три окна разом, и человек вернулся бы к списку.
    const under = {};
    const over = {};
    const closed = [];
    const leaveUnder = opened(under);
    const leaveOver = opened(over);

    modalPress(ESCAPE, under, { close: () => closed.push('под') });
    modalPress(ESCAPE, over, { close: () => closed.push('над') });

    expect(closed).toEqual(['над']);
    leaveOver();
    leaveUnder();
  });

  it('закрытое окно уступает клавиши тому, что под ним', () => {
    const under = {};
    const over = {};
    const closed = [];
    const leaveUnder = opened(under);
    opened(over)();

    modalPress(ESCAPE, under, { close: () => closed.push('под') });

    expect(closed).toEqual(['под']);
    leaveUnder();
  });

  it('окно без подтверждения на Enter не закрывается', () => {
    // У подборщика подтверждения нет вовсе: выбирают в нём мышью. Прими он
    // Enter за «закрыть» — окно захлопывалось бы на первом же нажатии в поиске.
    const mine = {};
    const leave = opened(mine);
    let closed = false;

    modalPress({ key: 'Enter', target: { tagName: 'INPUT' } }, mine, {
      close: () => (closed = true),
    });

    expect(closed).toBe(false);
    leave();
  });
});

describe('запись набранного клавишами', () => {
  it('Ctrl+Enter отправляет набранное, не дожидаясь паузы', () => {
    // Заметка пишется с задержкой; человеку, который хочет записать её сейчас,
    // иначе остаётся только уйти из поля мышью.
    expect(saveKey({ key: 'Enter', ctrlKey: true })).toBe(true);
  });

  it('то же делает Cmd+Enter', () => {
    expect(saveKey({ key: 'Enter', metaKey: true })).toBe(true);
  });

  it('один Enter переносит строку, а не записывает', () => {
    // Заметку набирают в несколько абзацев: запись по Enter обрывала бы её на
    // первом же переводе строки.
    expect(saveKey({ key: 'Enter' })).toBe(false);
  });

  it('прочие клавиши записи не просят', () => {
    expect(saveKey({ key: 's', ctrlKey: true })).toBe(false);
  });
});
