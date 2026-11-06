// Профили: перечень моста строками окна выбора и замок удаления.
//
// Чистые функции: ответ моста приходит доводом, наружу уходят строки. Ни моста,
// ни разметки этот файл не знает.

import { RUNNING } from './progress.js';

/** Тот же отказ, что у моста: кнопка говорит его заранее, а не плашкой после. */
const LAST_PROFILE = 'Это единственный профиль';

/** Профили строками окна — в порядке моста.
 *
 * Довод — `items` ответа `workspaces.list`. Активный профиль помечен нынешним:
 * сменить профиль на тот же самый значило бы перечитать всё впустую.
 */
export function workspaceChoices(items) {
  return items.map((one) => ({ key: one.id, label: one.name, current: one.active }));
}

/** Чем заперто удаление текущего профиля; пусто — не заперто. */
export function removalLock(items, running) {
  if (running) return RUNNING;
  return items.length === 1 ? LAST_PROFILE : '';
}

/** Способы заведения профиля строками окна; ключ — то, что ждёт `workspaces.create`. */
export const CREATE_WAYS = [
  { key: 'empty', label: 'Пустой профиль' },
  { key: 'copy', label: 'Полная копия текущего профиля' },
  { key: 'personal', label: 'Копия личных данных текущего профиля' },
];
