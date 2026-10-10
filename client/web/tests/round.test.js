// Общий учёт прогона: кого зовут в миг его конца.

import { describe, expect, it } from 'vitest';

import { hearRound, round } from '$state/round.svelte.js';

function bridge() {
  const handlers = {};
  return {
    on: (name, handler) => {
      handlers[name] = handler;
      return () => delete handlers[name];
    },
    fire: (name) => handlers[name]?.(),
  };
}

describe('конец прогона', () => {
  it('зовёт подписанного, когда шедший прогон кончился', () => {
    const events = bridge();
    const deaf = hearRound(events);
    let heard = 0;
    const off = round.onFinish(() => heard++);
    events.fire('ingestion_started');
    events.fire('ingestion_finished');
    expect(heard).toBe(1);
    off();
    deaf();
  });

  it('конец без начала не зовёт: окно открылось, а прогон шёл в прошлом', () => {
    const events = bridge();
    const deaf = hearRound(events);
    let heard = 0;
    const off = round.onFinish(() => heard++);
    events.fire('ingestion_finished');
    expect(heard).toBe(0);
    off();
    deaf();
  });

  it('отписанного не зовёт', () => {
    const events = bridge();
    const deaf = hearRound(events);
    let heard = 0;
    round.onFinish(() => heard++)();
    events.fire('ingestion_started');
    events.fire('ingestion_finished');
    expect(heard).toBe(0);
    deaf();
  });
});
