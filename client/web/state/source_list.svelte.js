// Список источников вакансий — каналов или агрегаторов: чтение с поиском,
// строчный переключатель и общий выключатель над ними.
//
// Своим объявлением, потому что вкладки каналов и агрегаторов вели список
// одинаково и расходились бы молча. Со страничным списком контактов
// (`paged_list`) не сведено: источники приходят разом, без страниц, и у них
// есть общий выключатель, которого у людей и компаний нет.
//
// Имён методов моста здесь нет: зовы приходят обёртками, чтобы имя стояло на
// шве, в самой вкладке. Заходит вкладка общим `contacts_watch`.

import { freshAnswer } from '$state/fresh.js';

/** Заводит список источников.
 *
 * `alive` — признак жизни вкладки (`alive.js`); `read(search)` — чтение списка;
 * `key` — под каким именем строки лежат в ответе; `setActive(row, on)` и
 * `setAll(on)` — переключатели. Отказ моста — пустота: плашку он уже показал.
 */
export function sourceList({ alive, read, key, setActive, setAll }) {
  let loaded = $state(false);
  let rows = $state([]);
  // Общий выключатель вида: свой, поверх строк, и строк он не трогает.
  let enabled = $state(true);
  let search = $state('');
  let answer = $state(null);

  // Счёт попыток свой: поиск набирают посимвольно, ответы доезжают вразнобой,
  // и старый, лёгший поверх свежего, показал бы строки, которых уже не ищут.
  const fresh = freshAnswer(() => alive.now);

  async function again() {
    const now = await fresh(() => read(search));
    if (now === null) return;
    rows = now[key];
    enabled = now.enabled;
    answer = now;
    loaded = true;
  }

  /** Переключить и перечитать; отвечает, легло ли — переключатель держит
   *  положение у себя, и без ответа отказ остался бы невидимым. */
  async function switched(done) {
    const result = await done;
    await again();
    return result !== null;
  }

  return {
    get loaded() {
      return loaded;
    },
    get rows() {
      return rows;
    },
    get enabled() {
      return enabled;
    },
    get search() {
      return search;
    },
    /** Последний принятый ответ целиком: сверх строк вкладка берёт из него своё. */
    get answer() {
      return answer;
    },
    again,
    find(text) {
      search = text;
      return again();
    },
    toggle: (row, on) => switched(setActive(row, on)),
    toggleAll: (on) => switched(setAll(on)),
    /** Заход на вкладку: прочитать список и отдать снятие (`contacts_watch`). */
    entered: () => alive.entered(again),
  };
}
