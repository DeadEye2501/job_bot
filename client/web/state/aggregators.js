// Агрегаторы, переведённые в то, что видно: подписи, переключатели и запор
// действий агента.
//
// Чистые функции: строки моста приходят доводами, наружу уходят строки и
// признаки. Ни моста, ни разметки этот файл не знает.

import { showStamp } from './dates.js';
import { BLOCKED_TITLE, sourceBlock, sourceToggle } from './sources.js';

/** Где агрегатор ищет — подпись под именем.
 *
 * У «Поиска по сети» адреса нет — его место занимает то, где он ищет: пустое
 * место под именем читалось бы как недозаведённый агрегатор.
 */
export function aggregatorWhere(row) {
  return row.is_web_search ? 'по всей сети' : row.host;
}

/** Когда агрегатор обходили в последний раз. */
export function aggregatorLastRun(row) {
  return row.last_run_at ? `Обход ${showStamp(row.last_run_at)}` : 'Ещё не обходили';
}

/** Чем заперт агрегатор без входа — и переключатель строки, и прогон из карточки. */
export const LOGIN_FIRST = 'Сначала войдите на сайт';

/** Переключатель обхода в строке агрегатора; `enabled` — общий выключатель.
 *
 * Заперт из отсева и без входа: без входа обход встанет на первой же странице
 * сайта (`sources.sourceToggle`). Отсев старше входа: снять запись — первое,
 * что придётся сделать, и «войдите на сайт» в этот миг посылало бы не туда.
 */
export function aggregatorToggle(row, enabled) {
  return sourceToggle(
    {
      active: row.is_active,
      open: row.is_logged_in && !row.is_blacklisted,
      lockTitle: row.is_blacklisted ? BLOCKED_TITLE : LOGIN_FIRST,
    },
    enabled,
  );
}

/** Чем заперты действия агента — вход и прогон; пусто — не заперты.
 *
 * Старшинство — общее у источников (`sources.sourceBlock`). Обход здесь стоит
 * раньше слов моста ещё и затем, что «нет браузера» в этот миг сбивало бы —
 * браузер есть, он просто занят.
 */
export function actionBlock({ blocked = false, running, lock, lockedTip }) {
  // Слово в слово с отказом моста на те же вход и прогон (`refusals.py`).
  const barred = blocked ? 'В чёрном списке — снимите запись, чтобы работать с сайтом' : '';
  return sourceBlock({ barred, running, lock, lockedTip });
}
