// @vitest-environment jsdom
//
// Куда надо попасть, чтобы открыть канал.
//
// Открывает вся строка целиком: нажатие на одном имени оставляет мёртвыми оба
// отступа строки, кружок и хвост со счётчиком, а между соседними строками из
// отступов набирается сплошная неотзывчивая полоса.
//
// Переключатель опроса из этого исключён обеими дорогами ввода: он в строке сам
// себе нажатие.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

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

/** Строка канала с записанными нажатиями. */
function row() {
  const picked = [];
  const shown = render(ChannelRow, {
    props: {
      channel: CHANNEL,
      onpick: () => picked.push(CHANNEL.id),
      ontoggle: async () => true,
    },
  });
  return { picked, root: shown.container.querySelector('.cnt-hr-row') };
}

describe('живая строка канала', () => {
  it('открывает канал нажатием по самой строке, а не только по имени', async () => {
    const { picked, root } = row();

    root.click();
    await settled();

    expect(picked).toEqual([7]);
  });

  it('нажатие по кружку канала тоже открывает канал', async () => {
    const { picked, root } = row();

    root.querySelector('.hr-avatar').click();
    await settled();

    expect(picked).toEqual([7]);
  });

  it('нажатие по счёту вакансий тоже открывает канал', async () => {
    const { picked, root } = row();

    root.querySelector('.cnt-co-count').click();
    await settled();

    expect(picked).toEqual([7]);
  });

  it('открывает канал клавишей, а не только мышью', async () => {
    const { picked, root } = row();

    root.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await settled();

    expect(picked).toEqual([7]);
  });

  it('переключатель опроса канал не открывает', async () => {
    const { picked, root } = row();

    root.querySelector('input[type="checkbox"]').click();
    await settled();

    expect(picked).toEqual([]);
  });

  it('клавиша на переключателе опроса канал не открывает', async () => {
    const { picked, root } = row();

    root
      .querySelector('input[type="checkbox"]')
      .dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await settled();

    expect(picked).toEqual([]);
  });
});
