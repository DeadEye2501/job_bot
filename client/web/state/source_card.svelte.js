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
import { sourceVacancies } from '$state/source_vacancies.svelte.js';

/** Заходит на карточку источника и отдаёт снятие.
 *
 * `alive` — признак жизни карточки (`alive.js`), `id` — открытый источник.
 * `forget` убирает показанное прежним: панель одна, и его числа под новым
 * именем читались бы как числа нового. `read(id)` читает карточку с её
 * вакансиями — и на заходе, и по вести: обход приносит вакансии, пока карточка
 * открыта, и смотрит прогнавший человек именно на них.
 */
export function watchSourceCard(events, alive, id, { forget, read }) {
  const settled = alive.entered(() => {
    forget();
    read(id);
  });
  const deaf = events.on('vacancies_list_changed', () => read(id));
  return () => {
    settled();
    deaf();
  };
}

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
