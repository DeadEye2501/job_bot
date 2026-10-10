// @vitest-environment jsdom
//
// Куда надо попасть, чтобы открыть источник — канал или агрегатор.
//
// Открывает вся строка целиком: нажатие на одном имени оставляет мёртвыми оба
// отступа строки, кружок и хвост со счётчиком, а между соседними строками из
// отступов набирается сплошная неотзывчивая полоса.
//
// Переключатель опроса из этого исключён обеими дорогами ввода: он в строке сам
// себе нажатие.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import AggregatorRow from '../components/AggregatorRow.svelte';
import ChannelRow from '../components/ChannelRow.svelte';
import { settled } from './settled.js';

afterEach(cleanup);

const CHANNEL = {
  id: 7,
  title: 'Работа для флористов',
  username: 'flower_jobs',
  avatar: null,
  is_active: true,
  is_blacklisted: false,
  vacancy_count: 3,
};

const AGGREGATOR = {
  id: 7,
  name: 'Example',
  host: 'example.test',
  avatar: null,
  is_web_search: false,
  is_active: true,
  is_logged_in: true,
  is_blacklisted: false,
  vacancy_count: 3,
};

// Строки двух родов собраны на одной общей, и нажатия обязаны вести себя
// одинаково в обеих.
const KINDS = [
  ['канала', ChannelRow, { channel: CHANNEL }],
  ['агрегатора', AggregatorRow, { row: AGGREGATOR }],
];

describe.each(KINDS)('живая строка %s', (_kind, Row, subject) => {
  /** Строка с записанными нажатиями. */
  function row() {
    const picked = [];
    const shown = render(Row, {
      props: {
        ...subject,
        enabled: true,
        onpick: () => picked.push(7),
        ontoggle: async () => true,
      },
    });
    return { picked, root: shown.container.querySelector('.cnt-hr-row') };
  }

  it('открывает источник нажатием по самой строке, а не только по имени', async () => {
    const { picked, root } = row();

    root.click();
    await settled();

    expect(picked).toEqual([7]);
  });

  it('нажатие по кружку тоже открывает источник', async () => {
    const { picked, root } = row();

    root.querySelector('.hr-avatar').click();
    await settled();

    expect(picked).toEqual([7]);
  });

  it('нажатие по счёту вакансий тоже открывает источник', async () => {
    const { picked, root } = row();

    root.querySelector('.cnt-co-count').click();
    await settled();

    expect(picked).toEqual([7]);
  });

  it('открывает источник клавишей, а не только мышью', async () => {
    const { picked, root } = row();

    root.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await settled();

    expect(picked).toEqual([7]);
  });

  it('переключатель обхода источник не открывает', async () => {
    const { picked, root } = row();

    root.querySelector('input[type="checkbox"]').click();
    await settled();

    expect(picked).toEqual([]);
  });

  it('клавиша на переключателе обхода источник не открывает', async () => {
    const { picked, root } = row();

    root
      .querySelector('input[type="checkbox"]')
      .dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await settled();

    expect(picked).toEqual([]);
  });
});
