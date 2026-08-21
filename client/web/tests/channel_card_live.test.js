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
import { settled } from './settled.js';

afterEach(cleanup);

const CARD = {
  channel_id: 9,
  username: 'python_cool',
  title: 'Python Cool',
  avatar: null,
  blacklist_value: null,
  stats: {
    total: 0,
    vacancies_per_day: 0,
    fit_percent: null,
    apply_percent: null,
    response_percent: null,
    status_counts: {},
  },
};

function screen() {
  const asked = [];
  const shown = render(ChannelCard, {
    props: {
      ask: async (method) => {
        asked.push(method);
        if (method === 'channels.detail') return CARD;
        return { vacancies: [], has_more: false };
      },
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
  return asked.filter((one) => one === method).length;
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
});
