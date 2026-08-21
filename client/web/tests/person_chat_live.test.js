// @vitest-environment jsdom
//
// Перечитывание переписки по вести о новом письме.
//
// Хвост спрашивался без потолка — то есть всегда последние полсотни писем, — и
// клался в ленту заменой. Человек, долиставший переписку до начала разговора,
// на первом же входящем оказывался снова на последних пятидесяти: читать
// историю во время живой переписки было нельзя. Соседние перечни от этого
// заслонены потолком по показанному (`refreshLimit`), у переписки его не было.

import { cleanup, render } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import PersonChat from '../app/PersonChat.svelte';

afterEach(cleanup);

function letter(id) {
  return {
    id,
    is_incoming: true,
    is_deleted: false,
    text: `письмо ${id}`,
    sent_at: '2026-08-20T10:00:00+03:00',
    is_read: true,
    media_kind: null,
    media_path: null,
  };
}

/** Переписка с записанными за ней просьбами к мосту. */
function chat(shownCount) {
  const asked = [];
  const listeners = {};
  const messages = Array.from({ length: shownCount }, (_, i) => letter(i + 1));

  const ask = async (method, payload) => {
    asked.push({ method, payload });
    if (method === 'hr.messages') return { messages, has_more: true, ...payload };
    if (method === 'hr.mark_read') return { updated: 0 };
    return {};
  };
  const events = {
    on: (name, fn) => {
      listeners[name] = fn;
      return () => delete listeners[name];
    },
  };

  render(PersonChat, {
    props: { ask, say: () => {}, hrId: 7, blocked: false, events, onread: () => {} },
  });
  return { asked, listeners };
}

/** Дождаться, пока осядут цепочка ответов моста и отрисовка. */
async function settled() {
  for (let i = 0; i < 6; i += 1) {
    await tick();
    await new Promise((done) => setTimeout(done, 0));
  }
}

describe('живая переписка', () => {
  it('по вести просит не меньше показанного, а не последние полсотни', async () => {
    // Пролистанное вверх — это показанное: спроси мост меньше, и дочитанное
    // пропадёт, потому что лента кладёт пришедшее заменой.
    const { asked, listeners } = chat(120);
    await settled();

    listeners.contacts_hr_messages_arrived({ hr_id: 7 });
    await settled();

    const last = asked.filter((one) => one.method === 'hr.messages').pop();
    expect(last.payload.limit).toBeGreaterThanOrEqual(120);
  });
});
