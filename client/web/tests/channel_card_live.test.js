// @vitest-environment jsdom
//
// Карточка канала, открытая нажатием по строке списка.
//
// Смотрят на неё двумя мерами. Первая — счёт зовов моста: по разу за вопрос,
// иначе это круг. Эффект, который пишет состояние и тут же сам его читает,
// Svelte перезаводит заново, и каждый оборот шлёт мосту два зова, отчего окно
// встаёт намертво. Вторая — то, что панель вообще дорисовывается: в круге она
// остаётся на «Загрузка…» навсегда.
//
// Слоты моста тут не предмет: они покрыты своими проверками.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import ChannelCard from '../app/ChannelCard.svelte';
import { hearRound } from '../state/round.svelte.js';
import { answering, roundGoes } from './bridge_stub.js';
import { settled } from './settled.js';
import { EMPTY_STATS } from './stats_stub.js';

afterEach(cleanup);

const CARD = {
  channel_id: 9,
  username: 'python_cool',
  title: 'Python Cool',
  avatar: null,
  blacklist_value: null,
  stats: EMPTY_STATS,
};

function screen() {
  const { asked, ask } = answering((method) =>
    method === 'channels.detail' ? CARD : { vacancies: [], has_more: false },
  );
  const shown = render(ChannelCard, {
    props: {
      ask,
      say: () => {},
      lockedTip: '',
      events: { on: () => () => {} },
      channelId: CARD.channel_id,
      onvacancy: () => {},
      onclose: () => {},
      onchanged: () => {},
    },
  });
  return { asked, shown };
}

/** Сколько раз спросили названный слот. */
function times(asked, method) {
  return asked.filter((one) => one.method === method).length;
}

describe('живая карточка канала', () => {
  it('спрашивает мост по разу на открытый канал', async () => {
    const { asked } = screen();
    await settled();

    expect(times(asked, 'channels.detail')).toBe(1);
    expect(times(asked, 'channels.vacancies')).toBe(1);
  });

  it('дорисовывается до самого канала', async () => {
    const { shown } = screen();
    await settled();

    expect(shown.container.textContent).toContain('Python Cool');
  });

  it('во время обхода «Прогнать сейчас» заперт и называет обход', async () => {
    roundGoes();
    const { shown } = screen();
    await settled();

    shown.container.querySelector('button[title="Действия"]').click();
    await settled();
    const poll = [...document.querySelectorAll('.menu-item')].find((one) =>
      one.textContent.includes('Прогнать сейчас'),
    );

    expect([poll.disabled, poll.title]).toEqual([true, 'Идёт обход']);
    hearRound({ on: () => () => {} });
  });
});
