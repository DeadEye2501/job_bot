// Следствия одной летящей записи: что уезжает на мост, когда правок больше,
// чем ответов.
//
// Перечни анкеты мост принимает целиком и заменяет ими прежние. Значит две
// записи в полёте — это две замены, и порядок их прибытия решает, что
// останется в базе.

import { describe, expect, it } from 'vitest';

import { oneWrite } from '../state/one_write.js';

/** Запись, которая отвечает не сразу: ответ отдаёт вызывающий. */
function held() {
  const sent = [];
  const answers = [];
  return {
    sent,
    answers,
    write: (payload) => {
      sent.push(payload);
      return new Promise((resolve) => answers.push(resolve));
    },
  };
}

describe('одна летящая запись', () => {
  it('первая уезжает сразу', async () => {
    const { sent, write } = held();
    const push = oneWrite(write);

    push('раз');

    expect(sent).toEqual(['раз']);
  });

  it('пока первая летит, вторая ждёт её ответа', async () => {
    // Иначе мост получает две замены разом, и в базе остаётся та, что пришла
    // второй, — а это может быть и более старый снимок.
    const { sent, answers, write } = held();
    const push = oneWrite(write);

    push('раз');
    push('два');
    expect(sent).toEqual(['раз']);

    answers[0]();
    await Promise.resolve();
    await Promise.resolve();

    expect(sent).toEqual(['раз', 'два']);
  });

  it('набежавшие сводятся к последнему снимку', async () => {
    // Человек правит поле за полем, пока ответ идёт: промежуточные снимки уже
    // не нужны — перечень уезжает целиком, и последний включает их все.
    const { sent, answers, write } = held();
    const push = oneWrite(write);

    push('раз');
    push('два');
    push('три');
    answers[0]();
    await Promise.resolve();
    await Promise.resolve();

    expect(sent).toEqual(['раз', 'три']);
  });

  it('ожидание кончается вместе с записью', async () => {
    // Зовущий ждёт своей записи: на этом ожидании держится и «уходим с
    // вкладки, дошли ли правки».
    const { answers, write } = held();
    const push = oneWrite(write);

    let done = false;
    const waiting = push('раз').then(() => (done = true));
    expect(done).toBe(false);

    answers[0]();
    await waiting;

    expect(done).toBe(true);
  });

  it('ожидающий узнаёт исход той записи, что уехала за него', async () => {
    // Снимки сведены к последнему, и «легло ли» — это про него: набранное
    // раньше в него и вошло. Отложенная запись по этому ответу решает, считать
    // ли набранное записанным.
    const answers = [];
    const push = oneWrite(
      (payload) => new Promise((resolve) => answers.push(() => resolve(payload === 'три'))),
    );

    const first = push('раз');
    push('два');
    push('три');
    answers[0]();
    await Promise.resolve();
    await Promise.resolve();
    answers[1]();

    expect(await first).toBe(true);
  });

  it('отказ записи не запирает следующие', async () => {
    // Мост отвечает отказом на недозаполненную анкету — это обычное дело, и
    // после него человек дописывает поле и записывает снова. Отказ приходит
    // ответом, а не броском: все трое зовущих ловят его у себя.
    const sent = [];
    const push = oneWrite(async (payload) => {
      sent.push(payload);
      return false;
    });

    await push('раз');
    await push('два');

    expect(sent).toEqual(['раз', 'два']);
  });

  it('отказ первой записи не теряет ту, что встала за ней', async () => {
    // Человек правит следующее поле, пока отказ ещё в пути: его снимок свежее
    // отказанного, и потеряй мы его — правка пропала бы вместе с ответом.
    const sent = [];
    const answers = [];
    const push = oneWrite((payload) => {
      sent.push(payload);
      return new Promise((resolve) => answers.push(() => resolve(false)));
    });

    push('раз');
    push('два');
    answers[0]();
    await Promise.resolve();
    await Promise.resolve();

    expect(sent).toEqual(['раз', 'два']);
  });
});
