// Общий учёт прогона: кого зовут в миг его конца и ждёт ли прогон человека.

import { describe, expect, it } from 'vitest';

import { hearRound, round } from '$state/round.svelte.js';

function bridge() {
  const handlers = {};
  return {
    on: (name, handler) => {
      handlers[name] = handler;
      return () => delete handlers[name];
    },
    fire: (name, payload) => handlers[name]?.(payload),
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

describe('ожидание человека', () => {
  it('приходит с родом и сайтом и уходит, когда человек справился', () => {
    const events = bridge();
    const deaf = hearRound(events);
    events.fire('ingestion_started');
    events.fire('human_needed', { kind: 'captcha', host: 'site.test' });
    expect(round.human).toEqual({ kind: 'captcha', host: 'site.test' });
    events.fire('human_resolved');
    expect(round.human).toBeNull();
    deaf();
  });

  it('уходит и с концом прогона: остановленный обход о человеке больше не скажет', () => {
    const events = bridge();
    const deaf = hearRound(events);
    events.fire('ingestion_started');
    events.fire('human_needed', { kind: 'login', host: 'site.test' });
    events.fire('ingestion_finished');
    expect(round.human).toBeNull();
    deaf();
  });
});
