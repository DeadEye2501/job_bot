// Следствия окна выбора: когда выбранным можно связывать.

import { describe, expect, it } from 'vitest';

import { candidate, linkReady } from '../state/picker.js';

describe('запор кнопки «Связать»', () => {
  it('пока никого не выбрали, связывать нечем', () => {
    expect(linkReady({ current: 4, chosen: null })).toBe(false);
  });

  it('выбор того же, кто уже привязан, кнопку не отпирает', () => {
    // Иначе нажатие переписывает привязку тем же значением и пишет в журнал
    // перемену, которой не было.
    expect(linkReady({ current: 4, chosen: 4 })).toBe(false);
  });

  it('выбор другого отпирает кнопку', () => {
    expect(linkReady({ current: 4, chosen: 9 })).toBe(true);
  });

  it('выбор при пустой привязке отпирает кнопку', () => {
    expect(linkReady({ current: null, chosen: 9 })).toBe(true);
  });
});

describe('строка окна выбора', () => {
  it('подпись берётся готовым правилом предмета', () => {
    // Один и тот же человек, названный в списке и в подборщике по-разному,
    // читается как двое разных.
    expect(
      candidate({
        id: 4,
        icon: 'person',
        avatar: 'data:image/png;base64,x',
        line: { name: 'Ирина', sub: '@irina_hr · Ромашка' },
        count: 3,
        blocked: false,
      }),
    ).toEqual({
      id: 4,
      icon: 'person',
      avatar: 'data:image/png;base64,x',
      name: 'Ирина',
      sub: '@irina_hr · Ромашка',
      count: 3,
      blocked: false,
    });
  });

  it('снимка может не быть — на его месте встанет значок', () => {
    // У компании снимка нет вовсе, но поле остаётся: строка выбора одна на оба
    // предмета, и разбирать в ней два набора полей значило бы держать две.
    expect(
      candidate({
        id: 7,
        icon: 'domain',
        line: { name: 'Ромашка', sub: 'romashka.ru' },
        count: 0,
        blocked: true,
      }).avatar,
    ).toBe(null);
  });
});
