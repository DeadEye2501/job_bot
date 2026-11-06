// @vitest-environment jsdom
//
// Загрузка резюме с экрана анкеты: «Заменить» спрашивает способ — только
// прикрепить файл или разобрать его и заполнить анкету, — затем файл.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { answering, awaitingNews } from './bridge_stub.js';
import { buttonBy } from './press.js';
import { settled } from './settled.js';

vi.mock('$api/bridge.js', () => ({ call: () => Promise.resolve({}) }));

const { default: ProfileCv } = await import('../app/ProfileCv.svelte');

let deaf = () => {};

afterEach(() => {
  deaf();
  cleanup();
});

/** Анкета над мостом; `picked` — ответ диалога файла. */
async function sheet(picked = { path: 'C:/резюме.pdf' }) {
  const heard = awaitingNews();
  deaf = heard.deaf;
  const { asked, ask } = answering((method) => {
    if (method === 'profile.get') return { cv_meta: null, profile: null, photo_url: null };
    if (method === 'profile.pick') return picked;
    if (method === 'profile.parse_cv') return { started: true };
    return {};
  });
  const shown = render(ProfileCv, { props: { ask } });
  await settled();
  const finished = () => heard.finished({ action: 'parse_cv', message: 'Резюме разобрано' });
  return { asked, finished, shown, ask };
}

const replace = () => buttonBy('Заменить', { exact: true });
const rows = () => [...document.querySelectorAll('.choose-row')];
const names = () => rows().map((one) => one.querySelector('.picker-name').textContent.trim());
const methods = (asked) => asked.map(({ method }) => method);
const reads = (asked) => methods(asked).filter((one) => one === 'profile.get').length;

async function choose(at) {
  replace().click();
  await settled();
  rows()[at].click();
  await settled();
}

describe('загрузка резюме с экрана анкеты', () => {
  it('«Заменить» спрашивает способ узким окном, без подвала', async () => {
    const { asked } = await sheet();

    replace().click();
    await settled();

    expect(names()).toEqual(['Только прикрепить файл', 'Разобрать через LLM и заполнить профиль']);
    expect(document.querySelector('.choose-dialog').classList.contains('slim')).toBe(true);
    expect(buttonBy('Подтвердить')).toBeUndefined();
    expect(methods(asked)).not.toContain('profile.pick');
  });

  it('«Только прикрепить» берёт файл и перечитывает анкету, не разбирая', async () => {
    const { asked } = await sheet();
    const before = reads(asked);

    await choose(0);

    expect(methods(asked)).toContain('profile.pick');
    expect(methods(asked)).not.toContain('profile.parse_cv');
    expect(reads(asked)).toBe(before + 1);
    expect(rows()).toEqual([]);
  });

  it('разбор берёт файл, пускает разбор и перечитывает анкету по его концу', async () => {
    const { asked, finished } = await sheet();

    await choose(1);
    const picked = methods(asked).indexOf('profile.pick');
    expect(methods(asked).indexOf('profile.parse_cv')).toBeGreaterThan(picked);
    const before = reads(asked);

    finished();
    await settled();

    expect(reads(asked)).toBe(before + 1);
  });

  it('закрытый диалог файла ничего не разбирает', async () => {
    const { asked } = await sheet({ cancelled: true });

    await choose(1);

    expect(methods(asked)).not.toContain('profile.parse_cv');
  });

  it('пока идёт разбор, «Заменить» заперта и объясняет почему', async () => {
    const { finished } = await sheet();

    await choose(1);

    expect(replace().disabled).toBe(true);
    expect(replace().title).toBe('Идёт разбор резюме');
    finished();
    await settled();
    expect(replace().disabled).toBe(false);
  });

  it('экран, открытый заново посреди разбора, перечитывает анкету по его концу', async () => {
    const { finished, shown, ask, asked } = await sheet();
    await choose(1);
    shown.unmount();

    render(ProfileCv, { props: { ask } });
    await settled();
    expect(replace().disabled).toBe(true);
    const before = reads(asked);

    finished();
    await settled();

    expect(reads(asked)).toBe(before + 1);
  });
});
