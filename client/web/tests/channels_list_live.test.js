// @vitest-environment jsdom
//
// Слова отказа при заведении канала.
//
// Окно заведения сделано ровно ради них: ошибку в нике объясняют там же, где
// его набирали. Но зов шёл общей обёрткой, а та показывает плашку и отдаёт
// пустоту, — и в окно ложилась фраза «Не удалось добавить канал», из которой не
// следует ничего, а настоящие слова моста гасли в углу за 2,8 секунды.

import { cleanup, render, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

const refusals = [];

vi.mock('$api/bridge.js', () => ({
  call: (method, payload) => {
    const next = refusals.shift();
    if (next) return Promise.reject(next);
    return Promise.resolve({ created: true, username: payload.input });
  },
}));

const { default: ChannelsList } = await import('../app/ChannelsList.svelte');

afterEach(() => {
  refusals.length = 0;
  cleanup();
});

/** Дождаться, пока осядут ответы моста и отрисовка. */
async function settled() {
  for (let i = 0; i < 6; i += 1) {
    await tick();
    await new Promise((done) => setTimeout(done, 0));
  }
}

function screen() {
  const shown = render(ChannelsList, {
    props: {
      // Общая обёртка отвечает пустотой на отказ — она уже показала плашку и
      // погасит её через 2,8 секунды. Слова отказа через неё не проходят.
      ask: async (method) => (method === 'channels.create' ? null : { channels: [], has_more: false }),
      say: () => {},
      lockedTip: '',
      events: { on: () => () => {} },
      open: null,
      onopened: () => {},
      onvacancy: () => {},
    },
  });
  // Окно рисуется в тело страницы, мимо куска экрана: сверять надо тело.
  return { q: within(shown.container), body: () => document.body.textContent };
}

describe('живой список каналов', () => {
  it('кладёт под поле слова моста, а не общую фразу', async () => {
    refusals.push({ message: 'Telegram не нашёл канал @froda. Проверьте имя' });
    const { q, body } = screen();
    await settled();

    q.getByTitle('Добавить канал').click();
    await settled();
    const field = q.getByPlaceholderText('@username канала или t.me/...');
    field.value = '@froda';
    field.dispatchEvent(new Event('input', { bubbles: true }));
    await settled();
    q.getByText('Добавить').click();
    await settled();

    expect(body()).toContain('Telegram не нашёл канал @froda');
    expect(body()).not.toContain('Не удалось добавить канал');
  });
});
