// @vitest-environment jsdom
//
// Смена профиля с экрана анкеты: кнопка «Профили» открывает окно выбора, а
// нажатый профиль сразу становится активным и анкета перечитывается.

import { cleanup, render } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { hearRound } from '../state/round.svelte.js';
import { answering, roundGoes } from './bridge_stub.js';
import { buttonBy } from './press.js';
import { settled } from './settled.js';

vi.mock('$api/bridge.js', () => ({ call: () => Promise.resolve({}) }));

const { default: ProfileCv } = await import('../app/ProfileCv.svelte');

const LISTED = {
  items: [
    { id: 1, name: 'Python-разработчик', active: true },
    { id: 4, name: 'Без должности', active: false },
  ],
};

afterEach(() => {
  hearRound({ on: () => () => {} });
  cleanup();
});

/** Анкета над мостом, который знает эти профили. */
async function sheet() {
  const { asked, ask } = answering((method) => {
    if (method === 'workspaces.list') return LISTED;
    if (method === 'profile.get') return { cv_meta: null, profile: null, photo_url: null };
    return {};
  });
  render(ProfileCv, { props: { ask } });
  await settled();
  return asked;
}

async function openProfiles() {
  document.querySelector('[title="Профили"]').click();
  await settled();
}

const rows = () => [...document.querySelectorAll('.choose-row')];
const names = () => rows().map((one) => one.querySelector('.picker-name').firstChild.textContent);
const adding = () => document.querySelector('.choose-dialog .new-box');
const switched = (asked) =>
  asked.filter(({ method }) => method === 'workspaces.switch').map(({ payload }) => payload);

describe('окно профилей', () => {
  it('перечисляет профили, заведение нового — пунктирной кнопкой, подвала нет', async () => {
    await sheet();
    await openProfiles();

    expect(names()).toEqual(['Python-разработчик', 'Без должности']);
    expect(rows()[0].classList.contains('current')).toBe(true);
    expect(adding().textContent.trim()).toBe('+ Создать новый профиль');
    expect(document.querySelector('.choose-dialog').classList.contains('slim')).toBe(false);
    expect(buttonBy('Подтвердить')).toBeUndefined();
    expect(buttonBy('Отмена')).toBeUndefined();
  });

  it('нажатый профиль сразу становится активным, и анкета перечитывается', async () => {
    const asked = await sheet();
    await openProfiles();
    const readBefore = asked.filter(({ method }) => method === 'profile.get').length;

    rows()[1].click();
    await settled();

    expect(switched(asked)).toEqual([4]);
    expect(asked.filter(({ method }) => method === 'profile.get').length).toBe(readBefore + 1);
    expect(rows()).toEqual([]);
  });

  it('нажатие по текущему профилю ничего не меняет', async () => {
    const asked = await sheet();
    await openProfiles();

    rows()[0].click();
    await settled();

    expect(switched(asked)).toEqual([]);
  });

  it('пока идёт обход, профили и заведение заперты и объясняют почему', async () => {
    const asked = await sheet();
    await openProfiles();
    roundGoes();
    flushSync();

    expect(rows()[1].title).toBe('Идёт обход');
    expect(adding().disabled).toBe(true);
    expect(adding().title).toBe('Идёт обход');
    rows()[1].click();
    await settled();
    expect(switched(asked)).toEqual([]);
  });
});

const created = (asked) =>
  asked.filter(({ method }) => method === 'workspaces.create').map(({ payload }) => payload);

async function openWays() {
  await openProfiles();
  adding().click();
  await settled();
}

describe('окно заведения профиля', () => {
  it('открывается вместо окна профилей и предлагает три способа', async () => {
    await sheet();
    await openWays();

    expect(names()).toEqual([
      'Пустой профиль',
      'Полная копия текущего профиля',
      'Копия личных данных текущего профиля',
    ]);
    expect(adding()).toBeNull();
    expect(buttonBy('Подтвердить')).toBeUndefined();
    expect(document.querySelector('.choose-dialog').classList.contains('slim')).toBe(true);
  });

  it('нажатый способ сразу заводит профиль, и анкета перечитывается', async () => {
    const asked = await sheet();
    await openWays();
    const readBefore = asked.filter(({ method }) => method === 'profile.get').length;

    rows()[2].click();
    await settled();

    expect(created(asked)).toEqual(['personal']);
    expect(asked.filter(({ method }) => method === 'profile.get').length).toBe(readBefore + 1);
    expect(rows()).toEqual([]);
  });

  it('обход, начавшийся при открытом окне, запирает способы', async () => {
    const asked = await sheet();
    await openWays();
    roundGoes();
    flushSync();

    expect(rows()[0].title).toBe('Идёт обход');
    rows()[0].click();
    await settled();
    expect(created(asked)).toEqual([]);
  });
});
