// Вакансии в карточке источника — канала или агрегатора: страница, добор и
// перечитывание показанного.
//
// Своим объявлением, потому что карточки канала и агрегатора читали их
// дословно одинаково. Со списком контактов (`paged_list`) не сведено: у того
// поиск и признак «прочитан», а здесь источник сменяют нажатием по соседней
// строке, и показанное прежним сбрасывается разом.
//
// Имени метода моста здесь нет: чтение приходит обёрткой, чтобы имя стояло на
// шве, в самой карточке.

import { freshAnswer } from '$state/fresh.js';
import { appended, PAGE, refreshLimit } from '$state/paging.js';

/** Заводит вакансии карточки; `alive` — признак жизни её экрана (`alive.js`).
 *
 * `read(page)` — обёртка над мостом: получает `{limit, offset}`, отдаёт
 * страницу `{vacancies, has_more}` или пустоту.
 */
export function sourceVacancies(alive) {
  let rows = $state([]);
  let hasMore = $state(false);
  let digging = $state(false);

  // Свой счёт попыток: панель одна на всю вкладку, и ответ про прежний
  // источник, лёгший поверх свежего, показал бы его вакансии под новым именем.
  const fresh = freshAnswer(() => alive.now);

  async function load(read, page, put) {
    const answer = await fresh(() => read(page));
    if (answer === null) return;
    rows = put(answer.vacancies);
    hasMore = answer.has_more;
  }

  return {
    get rows() {
      return rows;
    },
    get hasMore() {
      return hasMore;
    },
    /** Идёт ли добор: под списком в это время крутится ожидание. */
    get digging() {
      return digging;
    },

    /** Перечитать с начала.
     *
     * Берёт столько строк, сколько показано, а не страницу: весть приходит на
     * каждое разобранное объявление, и страницей она схлопывала бы пролистанное
     * снова и снова — ровно во время того прогона, который человек и запустил.
     */
    reload(read) {
      return load(read, { limit: refreshLimit(rows.length), offset: 0 }, (page) => page);
    },

    /** Дочитать следующую страницу: панель подошла к концу. */
    async more(read) {
      if (!hasMore || digging) return;
      digging = true;
      try {
        await load(read, { limit: PAGE, offset: rows.length }, (page) => appended(rows, page));
      } finally {
        digging = false;
      }
    },

    /** Убрать показанное прежним источником: его вакансии под новым именем
     *  читались бы как вакансии нового. */
    clear() {
      rows = [];
      hasMore = false;
    },
  };
}
