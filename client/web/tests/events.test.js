// Следствия цикла живых событий: что доходит до экранов и когда он умолкает.
//
// Мост подделан вопросом-заглушкой: предмет здесь — сам цикл, а не дорога до
// питона, и она сторожится своими тестами.

import { describe, expect, it } from 'vitest';

import { listener } from '../api/events.js';

/** Мост, отвечающий заготовленным, а на исходе — закрытой очередью. */
function answers(...replies) {
  const asked = [];
  let step = 0;
  return {
    asked,
    ask: async (after) => {
      asked.push(after);
      const reply = replies[step] ?? { events: [], missed: false, closed: true };
      step += 1;
      if (reply instanceof Error) throw reply;
      return reply;
    },
  };
}

const news = (n, kind, payload = {}) => ({ n, kind, payload });

describe('цикл событий', () => {
  it('весть доходит до подписавшегося на её род', async () => {
    // Ради этого цикл и заведён: полоса прогресса, счётчик непрочитанного и
    // хвост журнала своих запросов не делают, они ждут вести.
    const bridge = answers({
      events: [news(1, 'unread_changed')],
      missed: false,
      closed: false,
    });
    const heard = [];
    const events = listener(bridge.ask);
    events.on('unread_changed', () => heard.push('слышал'));

    await events.run();

    expect(heard).toEqual(['слышал']);
  });

  it('чужой род до подписавшегося не доходит', async () => {
    // Стоит рядом с предыдущим нарочно: тот один был бы зелен и у цикла,
    // который зовёт всех подряд, — и каждый экран перерисовывался бы на любое
    // событие в приложении.
    const bridge = answers({
      events: [news(1, 'ingestion_started')],
      missed: false,
      closed: false,
    });
    const heard = [];
    const events = listener(bridge.ask);
    events.on('unread_changed', () => heard.push('слышал'));

    await events.run();

    expect(heard).toEqual([]);
  });

  it('первый вопрос идёт не с начала кольца, а с пустого места', async () => {
    // Номера у свежей страницы ещё нет: она только что открылась или
    // перезагрузилась. Спроси она с нуля — мост отдал бы кольцо целиком, и окно
    // мигнуло бы плашками часовой давности как свежими: «обход закончен»,
    // «письмо пришло», «отклик отправлен» — всё разом и всё уже неправда.
    const bridge = answers({ events: [], missed: false, closed: true });
    const events = listener(bridge.ask);

    await events.run();

    expect(bridge.asked).toEqual([null]);
  });

  it('второй вопрос идёт после последнего виденного номера', async () => {
    // Не продвинься номер, каждая пачка приезжала бы вечно, и экран
    // перерисовывался бы одним и тем же без остановки.
    const bridge = answers(
      { at: 7, events: [news(7, 'unread_changed')], missed: false, closed: false },
      { at: 7, events: [], missed: false, closed: true },
    );
    const events = listener(bridge.ask);

    await events.run();

    expect(bridge.asked).toEqual([null, 7]);
  });

  it('пустой ответ тоже двигает отметку', async () => {
    // Вопрос ждёт на той стороне до двадцати пяти секунд и возвращается пустым,
    // если за это время ничего не случилось. Останься отметка пустой, следующий
    // вопрос снова просил бы «с этого мига» — и всё, что легло между ответом и
    // вопросом, пропало бы молча, а потери мост бы не объявил.
    const bridge = answers(
      { at: 12, events: [], missed: false, closed: false },
      { at: 12, events: [], missed: false, closed: true },
    );
    const events = listener(bridge.ask);

    await events.run();

    expect(bridge.asked).toEqual([null, 12]);
  });

  it('закрытая очередь останавливает цикл, а не разгоняет его', async () => {
    // Окно закрывается, мост уходит. Не узнай цикл об этом, он спрашивал бы
    // мёртвый мост без передышки до самой смерти страницы.
    const bridge = answers({ events: [], missed: false, closed: true });
    const events = listener(bridge.ask);

    await events.run();

    expect(bridge.asked).toEqual([null]);
  });

  it('потеря объявляется отдельно от самих вестей', async () => {
    // Кольцо не бесконечно, и страница, вернувшаяся после перезагрузки, могла
    // пропустить середину. Промолчи цикл — экран остался бы врать, показывая
    // неполное как полное.
    const bridge = answers({
      events: [news(9, 'unread_changed')],
      missed: true,
      closed: false,
    });
    const losses = [];
    const events = listener(bridge.ask);
    events.on('missed', () => losses.push('потеря'));

    await events.run();

    expect(losses).toEqual(['потеря']);
  });

  it('сорвавшийся вопрос цикл не убивает', async () => {
    // Один отказ моста — не повод замолчать навсегда: события после него
    // перестали бы доходить вовсе, и человек не узнал бы об этом никак.
    const bridge = answers(
      new Error('мост икнул'),
      { events: [news(1, 'unread_changed')], missed: false, closed: false },
    );
    const heard = [];
    const events = listener(bridge.ask);
    events.on('unread_changed', () => heard.push('слышал'));

    await events.run();

    expect(heard).toEqual(['слышал']);
  });

  it('упавший слушатель не уносит с собой соседей по роду', async () => {
    // Один род вести слушают разные части экрана — полоса, счётчик, список.
    // Не перехвати цикл беду одного, остальные не узнали бы о вести вовсе, и
    // экран разошёлся бы с приложением молча.
    const bridge = answers({
      events: [news(1, 'unread_changed')],
      missed: false,
      closed: false,
    });
    const heard = [];
    const events = listener(bridge.ask);
    events.on('unread_changed', () => {
      throw new Error('первый упал');
    });
    events.on('unread_changed', () => heard.push('второй услышал'));

    await events.run();

    expect(heard).toEqual(['второй услышал']);
  });

  it('остановленный цикл больше не спрашивает', async () => {
    // Останавливают его при уходе страницы. Не остановись он, вопросы шли бы к
    // мосту, которого уже нет, до самой смерти окна.
    const bridge = answers(
      { events: [news(1, 'unread_changed')], missed: false, closed: false },
      { events: [], missed: false, closed: false },
    );
    const events = listener(bridge.ask);
    events.on('unread_changed', () => events.stop());

    await events.run();

    expect(bridge.asked).toEqual([null]);
  });

  it('отписавшийся больше не слышит', async () => {
    // Экран уходит, а подписка остаётся: без снятия она рисовала бы в
    // разметку, которой уже нет, и держала бы её от уборки.
    const bridge = answers({
      events: [news(1, 'unread_changed')],
      missed: false,
      closed: false,
    });
    const heard = [];
    const events = listener(bridge.ask);
    const off = events.on('unread_changed', () => heard.push('слышал'));
    off();

    await events.run();

    expect(heard).toEqual([]);
  });
});
