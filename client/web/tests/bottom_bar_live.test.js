// @vitest-environment jsdom
//
// Нижняя полоса как своя сборка.
//
// Жила она внутри оболочки — вместе с боковым меню и полем раздела, — и её
// десять состояний с десятью объявлениями делали самый большой файл фронта
// единственной точкой, которую правят и при добавлении раздела, и при любой
// правке полосы.
//
// Своей работы у полосы две, и обе видны только отсюда: часы здоровья, по
// которым зажигаются лампочки, и подсказка о запертых кнопках, которую ждут
// наверху — её раздают экранам.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import BottomBar from '../app/BottomBar.svelte';
import { hearRound } from '../state/round.svelte.js';
import { answering } from './bridge_stub.js';
import { settled } from './settled.js';

afterEach(cleanup);

function bar(health) {
  const tips = [];
  // Плашки полоса показывает не через мост, а через `say`: отказ запертого
  // тумблера виден только здесь.
  const said = [];
  // Вести полосе приходят подпиской: сюда складываются обработчики, чтобы
  // проверка могла позвать их так же, как их зовёт мост.
  const handlers = {};
  const { asked, ask } = answering((method, payload) => {
    if (method === 'system.initial') return { unread: { count: 0 }, mode: 'Full', health };
    if (method === 'system.set_mode') return { mode: payload };
    if (method === 'system.health') return health;
    return {};
  });

  const events = {
    on: (name, handler) => {
      handlers[name] = handler;
      return () => {};
    },
    run: () => {},
    stop: () => {},
  };
  // Вести о начале и конце прогона слушает общий учёт, а не полоса: в окне его
  // подписывает оболочка, здесь — проверка, на те же поддельные вести.
  hearRound(events);

  render(BottomBar, {
    props: {
      ask,
      say: (text) => said.push(text),
      events,
      onlocked: (tip) => tips.push(tip),
      oncontact: () => {},
    },
  });
  return { asked, tips, said, handlers };
}

describe('живая нижняя полоса', () => {
  it('разбор вставленного объявления называет себя под полосами', async () => {
    // Ступень эта счёта не имеет — полосы бегут пустыми, — и своё имя говорит
    // подписью. Не разбери полоса стадию, человек читал бы «Запуск…» всё
    // время разбора и не отличил бы свою вставку от обхода каналов.
    const { handlers } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    // Полоса показывает подпись только на идущей работе: до вести о начале
    // её место занято переключателем режима.
    handlers.ingestion_started();
    handlers.progress_update({
      stage: 'pasted',
      label: 'Разбор вставленного объявления…',
      current: 0,
      total: 0,
    });
    await settled();

    expect(document.body.textContent).toContain('Разбор вставленного объявления…');
  });

  it('гасит бота, когда что-то отвалилось, и называет наверх причину', async () => {
    // Бот, работающий против мёртвой системы, крутит обороты впустую, а
    // тумблер в этот миг уже заперт, и человек выключить его не может.
    const { asked, tips } = bar({ db: true, tg: false, chat: true, embed: true });
    await settled();

    expect(asked.some((one) => one.method === 'system.set_mode' && one.payload === 'Off')).toBe(true);
    expect(tips.at(-1)).toContain('TG');
  });

  it('запертый тумблер режима не переключает, а объясняет отказ', async () => {
    // Пока не жива хоть одна система, работать боту нечем, и смена режима
    // отдала бы человеку тумблер, за которым ничего не происходит. Молчать
    // при этом нельзя: запертую кнопку жмут именно затем, чтобы узнать почему.
    const { asked, said } = bar({ db: true, tg: false, chat: true, embed: true });
    await settled();
    const before = asked.filter((one) => one.method === 'system.set_mode').length;

    document.querySelector('.mode-control').click();
    await settled();

    expect(asked.filter((one) => one.method === 'system.set_mode')).toHaveLength(before);
    expect(said.at(-1)).toContain('TG');
  });

  it('при живых системах бота не трогает и подсказку отдаёт пустой', async () => {
    const { asked, tips } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    expect(asked.some((one) => one.method === 'system.set_mode')).toBe(false);
    expect(tips.at(-1)).toBe('');
  });

  it('ожидание человека встаёт плашкой на место полос', async () => {
    const { handlers } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    handlers.ingestion_started();
    handlers.human_needed({ kind: 'captcha', host: 'site.test' });
    await settled();

    expect(document.querySelector('.human-plate').textContent).toContain('Требуется пройти капчу');
    expect(document.querySelector('.progress-wrap')).toBeNull();
  });

  it('нажатие на плашку выводит браузер, галочка отпускает агента', async () => {
    const { asked, handlers } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();
    handlers.ingestion_started();
    handlers.human_needed({ kind: 'captcha', host: 'site.test' });
    await settled();

    document.querySelector('.human-plate-text').click();
    document.querySelector('.human-plate-done').click();
    await settled();

    const methods = asked.map((one) => one.method);
    expect(methods).toContain('system.reveal_browser');
    expect(methods).toContain('system.human_done');
  });

  it('ход обхода агрегатора идёт полосой каналов, со счётом в скобках', async () => {
    const { handlers } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    handlers.ingestion_started();
    handlers.progress_update({ stage: 'aggregator', label: 'hh.ru — найдено', current: 3, total: 10 });
    await settled();

    expect(document.querySelector('.progress-caption').textContent).toContain('hh.ru — найдено (3/10)');
  });

  it('слово обхода показывается плашкой', async () => {
    const { handlers, said } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    handlers.round_note({ text: 'Капча не пройдена — обход снят.' });

    expect(said).toContain('Капча не пройдена — обход снят.');
  });
});

