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
