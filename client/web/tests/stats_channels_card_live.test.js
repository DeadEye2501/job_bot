// @vitest-environment jsdom
//
// Строка воронки открывает свой источник в Контактах — кроме строки «Без
// канала»: открывать у неё нечего, и нажатие на ней не должно уводить с экрана.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import StatsChannelsCard from '../components/StatsChannelsCard.svelte';
import { settled } from './settled.js';

afterEach(cleanup);

/** Строка таблицы с нулями во всех колонках. */
function line(key, label, target) {
  return {
    key,
    label,
    target,
    total: 0,
    trash: 0,
    not_fit: 0,
    fit: 0,
    sent: 0,
    answered: 0,
    invite_plus: 0,
    decline: 0,
    conv_answ_sent: null,
    conv_invite_sent: null,
  };
}

const CHANNEL = { tab: 'channels', id: 7 };
const SITE = { tab: 'aggregators', id: 2 };

/** Таблица из канала, двух агрегаторов и строки без канала, с записанными нажатиями. */
function card() {
  const picked = [];
  const shown = render(StatsChannelsCard, {
    props: {
      channels: [
        line('channel:7', 'Канал', CHANNEL),
        line('aggregator:2', 'HeadHunter', SITE),
        line('aggregator:1', 'Поиск по сети', { tab: 'aggregators', id: 1 }),
        line('none:', 'Без канала', null),
      ],
      onpick: (target) => picked.push(target),
    },
  });
  const nameCell = (text) =>
    [...shown.container.querySelectorAll('.stats-ch-name-cell')].find(
      (cell) => cell.textContent.trim() === text,
    );
  return { picked, nameCell };
}

describe('живая таблица воронки по каналам', () => {
  it('строки агрегаторов показываются все', () => {
    const { nameCell } = card();

    expect(nameCell('HeadHunter')).toBeTruthy();
    expect(nameCell('Поиск по сети')).toBeTruthy();
  });

  it('строка канала открывает канал', async () => {
    const { picked, nameCell } = card();

    nameCell('Канал').click();
    await settled();

    expect(picked).toEqual([CHANNEL]);
  });

  it('строка агрегатора открывает агрегатор', async () => {
    const { picked, nameCell } = card();

    nameCell('HeadHunter').click();
    await settled();

    expect(picked).toEqual([SITE]);
  });

  it('строка без канала никуда не ведёт', async () => {
    const { picked, nameCell } = card();

    nameCell('Без канала').click();
    await settled();

    expect(picked).toEqual([]);
  });
});
