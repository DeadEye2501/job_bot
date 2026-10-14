// @vitest-environment jsdom
//
// Вкладка раздела переживает уход из раздела: открытую вкладку держит оболочка,
// экран раздела получает её параметром и отдаёт наружу выбор новой.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import ContactsScreen from '../app/ContactsScreen.svelte';
import ProfileScreen from '../app/ProfileScreen.svelte';
import { press } from './press.js';
import { settled } from './settled.js';

afterEach(cleanup);

async function shown(Screen, tab) {
  const picked = [];
  const view = render(Screen, {
    props: {
      ask: async () => null,
      say: () => {},
      lockedTip: '',
      events: { on: () => () => {} },
      openCard: null,
      onopened: () => {},
      onchosen: () => {},
      onvacancy: () => {},
      tab,
      ontab: (key) => picked.push(key),
    },
  });
  await settled();
  return {
    picked,
    active: () => view.container.querySelector('.top-tabs .tab.active').textContent.trim(),
    pick: (label) => press(label, { exact: true, among: '.top-tabs .tab' }),
  };
}

describe('вкладка раздела приходит снаружи', () => {
  it('контакты открываются на переданной вкладке', async () => {
    const { active } = await shown(ContactsScreen, 'aggregators');

    expect(active()).toBe('Агрегаторы');
  });

  it('выбор вкладки в контактах уходит наружу', async () => {
    const { picked, pick } = await shown(ContactsScreen, 'channels');

    pick('Компании');

    expect(picked).toEqual(['companies']);
  });

  it('профиль открывается на переданной вкладке', async () => {
    const { active } = await shown(ProfileScreen, 'skills');

    expect(active()).toBe('Skills');
  });

  it('выбор вкладки в профиле уходит наружу', async () => {
    const { picked, pick } = await shown(ProfileScreen, 'cv');

    pick('Projects');

    expect(picked).toEqual(['projects']);
  });
});
