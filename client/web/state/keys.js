// Кому из открытых окон достаётся нажатая клавиша и что она значит.
//
// Правила сняты с обработчика образца (main.html 15059–15065): решение
// принимается здесь, а окно только зовёт и делает.

const MULTILINE = new Set(['TEXTAREA']);

// Открытые окна снизу вверх. Порядок несущий: последнее открытое и есть то,
// на которое человек сейчас смотрит.
const OPEN = [];

/** Чем нажатая клавиша отзовётся в окне: закрытием, подтверждением или ничем.
 *
 * Многострочное поле — исключение: в нём Enter переносит строку. Иначе заметку
 * в два абзаца не набрать, первый же перевод строки отправил бы окно.
 */
export function modalKey(event) {
  if (event.key === 'Escape') return 'close';
  if (event.key === 'Enter' && !MULTILINE.has(event.target?.tagName)) return 'confirm';
  return null;
}

/** Отметить окно открытым; ответ — снятие отметки при закрытии.
 *
 * Окна встают друг на друга: слияние открывает подборщик поверх карточки, а
 * подтверждение — поверх подборщика. Слушают клавиатуру они все разом, и без
 * этой отметки один Escape закрыл бы всю стопку.
 */
export function opened(window_) {
  OPEN.push(window_);
  return () => {
    const at = OPEN.lastIndexOf(window_);
    if (at !== -1) OPEN.splice(at, 1);
  };
}

/** Отдать нажатие тому окну, которое сейчас наверху.
 *
 * Разбор один на все окна: пять диалогов повторили бы его пятью копиями и
 * разошлись бы первой же правкой.
 */
export function modalPress(event, window_, { close, confirm = null }) {
  if (OPEN.at(-1) !== window_) return;
  const said = modalKey(event);
  if (said === 'close') close();
  else if (said === 'confirm' && confirm) confirm();
}
