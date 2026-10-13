// Подставной мост для проверок: отвечает заготовленным, помнит зовы и шлёт
// вести так же, как настоящий.

import { hearRound } from '../state/round.svelte.js';

/** Подписка на вести моста: обработчики копятся по имени в `handlers`, `fire`
 *  зовёт их так же, как мост, `heard` говорит, слушают ли весть. */
export function listening() {
  const handlers = {};
  return {
    handlers,
    on: (name, handler) => {
      handlers[name] = handler;
      return () => delete handlers[name];
    },
    fire: (name, payload) => handlers[name]?.(payload),
    heard: (name) => name in handlers,
  };
}

/** Начать обход: его вести слушает общий учёт прогона, как в окне. Снимают
 *  учёт с подделки, подписав его на пустые вести (`hearRound({ on: … })`). */
export function roundGoes() {
  const events = listening();
  hearRound(events);
  events.fire('ingestion_started');
}

/** Мост, отвечающий заготовленным по очереди; зовы копятся в `asked`.
 *
 *  Заготовка-функция зовётся в миг ответа, а не заранее: так проверяются
 *  ответы, доезжающие не в том порядке, в каком их спросили.
 */
export function replying(answers) {
  return answering(() => {
    const next = answers.shift();
    return typeof next === 'function' ? next() : next;
  });
}

/** Мост, отвечающий функцией `answer(method, payload)`; зовы копятся в `asked`.
 *
 *  Отдельно от `replying`: там ответы идут очередью по одному на зов, а здесь —
 *  по имени метода, сколько бы раз и в каком порядке экран ни спрашивал.
 */
export function answering(answer) {
  const asked = [];
  const ask = async (method, payload) => {
    asked.push({ method, payload });
    return answer(method, payload);
  };
  return { asked, ask };
}

/** Мост, пишущий зов в общий след и всегда отвечающий одним и тем же.
 *
 *  Отдельно от `replying`: там зовы копятся своим списком, а здесь предмет —
 *  порядок между зовом, словами человеку и перечитыванием, и держит его один
 *  след на всё. Своим списком этот порядок не выражается вовсе.
 */
export function tracing(trail, answer) {
  return (method, payload) => {
    trail.push(`спрошено: ${method} ${JSON.stringify(payload)}`);
    return Promise.resolve(answer);
  };
}

/** Слово человеку, пишущее в тот же след. */
export function saying(trail) {
  return (text) => trail.push(`сказано: ${text}`);
}

/** Перечитывание списка, пишущее в тот же след. */
export function relisting(trail) {
  return () => trail.push('список перечитан');
}

/** Отложенное перечитывание карточки, пишущее в тот же след.
 *
 *  Отложено нарочно: сними кто-нибудь `await` перед ним, и список узнал бы о
 *  правке раньше самой карточки — а он-то и решает, что показывать.
 */
export function rereading(trail) {
  return async () => {
    await Promise.resolve();
    trail.push('карточка перечитана');
  };
}

/** Ответ моста, который держат в руке: отдают его, когда скажут, и тем, что
 *  скажут. */
export function held() {
  let release;
  const promise = new Promise((done) => (release = done));
  return { promise, give: (value) => release(value) };
}
