// Следствия чтения карточки правой панели: что ложится на экран, а что нет.
//
// Мост подделан: предмет здесь не он, а правила — чей ответ считается годным,
// что показывают при отказе и когда с экрана уходит прежняя беда.

import { describe, expect, it } from 'vitest';

import { cardRead } from '../state/card_read.js';
import { replying } from './bridge_stub.js';

function reader(answers, { alive = () => true } = {}) {
  const { asked, ask } = replying(answers);
  return {
    asked,
    read: cardRead({ ask, method: 'hr.detail', trouble: 'Не удалось прочитать карточку', alive }),
  };
}

describe('чтение карточки правой панели', () => {
  it('свежий ответ показывают как есть', async () => {
    const { asked, read } = reader([{ hr_id: 7, name: 'Ирина' }]);

    expect(await read(7)).toEqual({ card: { hr_id: 7, name: 'Ирина' }, trouble: '' });
    expect(asked).toEqual([{ method: 'hr.detail', payload: 7 }]);
  });

  it('отказ объясняют словами, а не пустой панелью', async () => {
    // Панель, застрявшая на «Загрузка…», не даёт даже перейти к соседней
    // записи: человек видит вечное ожидание вместо причины.
    const { read } = reader([null]);

    expect(await read(7)).toEqual({ card: null, trouble: 'Не удалось прочитать карточку' });
  });

  it('удача снимает прежнюю беду', async () => {
    // Строка отказа, оставшаяся поверх живых данных, читается как беда,
    // которой уже нет.
    const { read } = reader([null, { hr_id: 7 }]);

    await read(7);

    expect((await read(7)).trouble).toBe('');
  });

  it('устаревший ответ никуда не ложится', async () => {
    // Панель одна на всю вкладку, и записи в ней переключают нажатием по
    // соседней строке: ответ про прежнюю показал бы её числа под новым именем.
    let answerFirst;
    const { read } = reader([() => new Promise((resolve) => (answerFirst = resolve)), { hr_id: 8 }]);

    const slow = read(7);
    await read(8);
    answerFirst({ hr_id: 7 });

    expect(await slow).toBe(null);
  });

  it('ответ, доехавший после ухода с панели, никуда не ложится', async () => {
    // Класть его уже некуда: разметки нет, а положенное в снесённое состояние
    // всплывёт при следующем заходе поверх свежего.
    let gone = false;
    const { read } = reader([{ hr_id: 7 }], { alive: () => !gone });

    const going = read(7);
    gone = true;

    expect(await going).toBe(null);
  });
});
