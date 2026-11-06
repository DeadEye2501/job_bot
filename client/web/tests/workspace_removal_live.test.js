// @vitest-environment jsdom
//
// Удаление профиля из опасной зоны настроек: та же кнопка и то же
// подтверждение, что у «Удалить всё», и замки — обход и единственный профиль.

import { cleanup, render } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import SettingsScreen from '../app/SettingsScreen.svelte';
import { hearRound } from '../state/round.svelte.js';
import { answering, roundGoes } from './bridge_stub.js';
import { buttonBy, press } from './press.js';
import { settled } from './settled.js';

afterEach(() => {
  hearRound({ on: () => () => {} });
  cleanup();
});

const CREDS = { base_url: '', api_key: '', model: '' };

const SNAPSHOT = {
  tg: { api_id: '', api_hash: '', phone: '', has_password: false, has_session: false, username: '' },
  chat: CREDS,
  embed: CREDS,
  pipeline: {},
  aggregators: { aggregator_backfill_limit: 20 },
};

const TWO = [
  { id: 1, name: 'Python-разработчик', active: true },
  { id: 4, name: 'Без должности', active: false },
];

/** Экран настроек над мостом, который знает эти профили. */
async function screen(items = TWO) {
  const { asked, ask } = answering((method) => {
    if (method === 'settings.get') return SNAPSHOT;
    if (method === 'workspaces.list') return { items };
    return {};
  });
  render(SettingsScreen, { props: { ask, say: () => {} } });
  await settled();
  return asked;
}

const removeButton = () => buttonBy('Удалить профиль', { among: '.danger-row button' });
const confirmIn = () => buttonBy('Удалить профиль', { exact: true, among: '.modal-actions button' });
const told = (asked, name) => asked.filter(({ method }) => method === name).length;

describe('удаление профиля', () => {
  it('после подтверждения удаляет текущий профиль и перечитывает перечень', async () => {
    const asked = await screen();
    removeButton().click();
    await settled();

    expect(document.querySelector('.modal-message').textContent).toContain('«Python-разработчик»');
    const listedBefore = told(asked, 'workspaces.list');
    confirmIn().click();
    await settled();

    expect(told(asked, 'workspaces.remove')).toBe(1);
    expect(told(asked, 'workspaces.list')).toBe(listedBefore + 1);
    expect(document.querySelector('.modal-message')).toBeNull();
  });

  it('отмена ничего не удаляет', async () => {
    const asked = await screen();
    removeButton().click();
    await settled();

    press('Отмена', { exact: true });
    await settled();

    expect(told(asked, 'workspaces.remove')).toBe(0);
  });

  it('единственный профиль удалить нельзя, и кнопка говорит почему', async () => {
    await screen([TWO[0]]);

    expect(removeButton().disabled).toBe(true);
    expect(removeButton().title).toBe('Это единственный профиль');
  });

  it('пока идёт обход, кнопка заперта и объясняет почему', async () => {
    await screen();
    roundGoes();
    flushSync();

    expect(removeButton().disabled).toBe(true);
    expect(removeButton().title).toBe('Идёт обход');
  });

  it('обход, начавшийся при открытом подтверждении, запирает его', async () => {
    const asked = await screen();
    removeButton().click();
    await settled();
    roundGoes();
    flushSync();

    expect(confirmIn().disabled).toBe(true);
    confirmIn().click();
    await settled();
    expect(told(asked, 'workspaces.remove')).toBe(0);
  });
});
