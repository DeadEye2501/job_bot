// Следствия занесения карточки в отсев и снятия с него: что человек слышит и
// что обновляется после.

import { describe, expect, it } from 'vitest';

import { cardBlocking } from '../state/card_block.js';

import { relisting, rereading, saying, tracing } from './bridge_stub.js';

/** Карточка, записывающая всё, что с ней сделали. */
function card(answer, female = false) {
  const trail = [];
  const ask = tracing(trail, answer);
  const blocking = cardBlocking({
    block: (id) => ask('companies.block', id),
    unblock: (id) => ask('companies.unblock', id),
    female,
    say: saying(trail),
    reread: rereading(trail),
    onchanged: relisting(trail),
  });
  return { blocking, trail };
}

describe('отсев из карточки', () => {
  it('о занесении говорят, и карточка со списком узнают о нём', async () => {
    // Отметка отсева стоит в самой карточке и в её строке списка: не обнови
    // их, человек увидел бы прежнее и нажал бы второй раз.
    const one = card({ existed: false, was_inactive: false, value: '@ромашка' });

    await one.blocking.block(7);

    expect(one.trail).toEqual([
      'спрошено: companies.block 7',
      'сказано: Занесён в отсев: @ромашка',
      'карточка перечитана',
      'список перечитан',
    ]);
  });

  it('о компании говорят в женском роде', async () => {
    // «Занесён» про компанию человек читает как опечатку.
    const one = card({ existed: false, was_inactive: false, value: '@ромашка' }, true);

    await one.blocking.block(7);

    expect(one.trail).toContain('сказано: Занесена в отсев: @ромашка');
  });

  it('снятие отсева говорит своими словами', async () => {
    // Снятое и то, чего не было, названы по-разному: нажатие на записи,
    // которой нет в отсеве, иначе выглядит сделавшим работу.
    const one = card({ updated: true }, true);

    await one.blocking.unblock(7);

    expect(one.trail).toEqual([
      'спрошено: companies.unblock 7',
      'сказано: Убрана из отсева',
      'карточка перечитана',
      'список перечитан',
    ]);
  });

  it('о человеке при снятии говорят в мужском роде', async () => {
    // «Убрана» про человека читается как опечатка ровно так же, как «занесён»
    // про компанию.
    const one = card({ updated: true });

    await one.blocking.unblock(7);

    expect(one.trail).toContain('сказано: Убран из отсева');
  });

  it('снятие с того, чего в отсеве не было, названо иначе', async () => {
    // Нажатие на записи, которой в отсеве нет, иначе выглядит сделавшим
    // работу — и человек считает, что отсев снят, хотя снимать было нечего.
    const one = card({ updated: false });

    await one.blocking.unblock(7);

    expect(one.trail).toContain('сказано: В отсеве его не было');
  });

  it('отказ моста молчит и ничего не перечитывает', async () => {
    // Плашку об отказе человек уже увидел, а перечитанная карточка показала бы
    // то же самое — лишний зов ради того же вида.
    const one = card(null);

    await one.blocking.block(7);

    expect(one.trail).toEqual(['спрошено: companies.block 7']);
  });
});
