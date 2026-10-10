// Карточка источника вакансий — канала или агрегатора: её числа, вакансии и
// смена открытого источника.
//
// Своим объявлением, потому что карточки канала и агрегатора читали себя
// дословно одинаково. Своё у каждой — запоры, меню и шапка — остаётся в ней.
//
// Имён методов моста здесь нет: имя чтения карточки приходит доводом, чтение
// вакансий — обёрткой, чтобы оба стояли на шве, в самой карточке.

import { living } from '$state/alive.js';
import { cardRead } from '$state/card_read.js';
import { watchSourceCard } from '$state/contacts_watch.js';
import { sourceVacancies } from '$state/source_vacancies.svelte.js';

/** Заводит карточку источника.
 *
 * `method` — чтение карточки по номеру, `trouble` — слова его отказа;
 * `vacanciesOf(id)` — обёртка чтения страницы вакансий этого источника.
 */
export function sourceCard({ ask, method, trouble: refused, vacanciesOf }) {
  let card = $state(null);
  let trouble = $state('');

  // Свой счёт попыток на каждый вопрос: панель одна на всю вкладку, и
  // источник в ней переключают нажатием по соседней строке — ответ про
  // прежний, лёгший поверх свежего, показал бы его числа под новым именем.
  const alive = living();
  const vacancies = sourceVacancies(alive);

  const read = cardRead({
    ask,
    method,
    trouble: refused,
    alive: () => alive.now,
    show: (now) => ({ card, trouble } = now),
  });

  function reread(id) {
    read(id);
    vacancies.reload(vacanciesOf(id));
  }

  return {
    get card() {
      return card;
    },
    get trouble() {
      return trouble;
    },
    vacancies,
    /** Перечитать одни числа: отметка отсева, вход и время обхода. */
    read,
    /** Дочитать следующую страницу вакансий открытого источника. */
    more: (id) => vacancies.more(vacanciesOf(id)),
    /** Зайти на источник и отдать снятие — его возвращают из эффекта. */
    watch: (events, id) =>
      watchSourceCard(events, alive, id, {
        forget: () => {
          card = null;
          trouble = '';
          vacancies.clear();
        },
        read: reread,
      }),
  };
}
