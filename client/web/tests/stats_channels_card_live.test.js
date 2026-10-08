// @vitest-environment jsdom
//
// Строка воронки открывает свой канал в Контактах — кроме строки «Без канала»:
// открывать у неё нечего, и нажатие на ней не должно уводить с экрана.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import StatsChannelsCard from '../components/StatsChannelsCard.svelte';
import { settled } from './settled.js';

afterEach(cleanup);

/** Строка таблицы с нулями во всех колонках. */
function line(id, label) {
  return {
    id,
    label,
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

/** Таблица из канала и строки без канала, с записанными нажатиями. */
function card() {
  const picked = [];
  const shown = render(StatsChannelsCard, {
    props: {
      channels: [line(7, 'Канал'), line(null, 'Без канала')],
      onpick: (id) => picked.push(id),
    },
  });
  const nameCell = (text) =>
    [...shown.container.querySelectorAll('.stats-ch-name-cell')].find(
      (cell) => cell.textContent.trim() === text,
    );
  return { picked, nameCell };
}

describe('живая таблица воронки по каналам', () => {
  it('строка канала открывает канал', async () => {
    const { picked, nameCell } = card();

    nameCell('Канал').click();
    await settled();

    expect(picked).toEqual([7]);
  });

  it('строка без канала никуда не ведёт', async () => {
    const { picked, nameCell } = card();

    nameCell('Без канала').click();
    await settled();

    expect(picked).toEqual([]);
  });
});
