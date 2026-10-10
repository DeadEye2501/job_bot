// Подставной мост для проверок состояния: отвечает заготовленным и помнит зовы.
//
// Заготовки разбираются по очереди, по одной на зов. Заготовка-функция зовётся
// в миг ответа, а не заранее: так проверяются ответы, доезжающие не в том
// порядке, в каком их спросили, — а их проверяют оба потребителя.

/** Мост, отвечающий заготовленным по очереди; зовы копятся в `asked`. */
export function replying(answers) {
  const asked = [];
  const ask = async (method, payload) => {
    asked.push({ method, payload });
    const next = answers.shift();
    return typeof next === 'function' ? next() : next;
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

/** Ответ моста, который держат в руке: отдают его, когда скажут. */
export function held(value) {
  let release;
  const promise = new Promise((done) => (release = done));
  return { promise, give: () => release(value) };
}
