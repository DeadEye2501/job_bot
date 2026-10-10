// Карточка источника вакансий — канала или агрегатора: её числа, вакансии и
// смена открытого источника.
//
// Своим объявлением, потому что карточки канала и агрегатора читали себя
// дословно одинаково. Сама карточка с её сменой — общая с людьми и компаниями
// (`pane_card`); здесь сверх неё листаемые вакансии и перечитывание по вести.
// Своё у каждой — запоры, меню и шапка — остаётся в ней.
//
// Имён методов моста здесь нет: имя чтения карточки приходит доводом, чтение
// вакансий — обёрткой, чтобы оба стояли на шве, в самой карточке.

import { paneCard } from '$state/pane_card.svelte.js';
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
export function sourceCard({ ask, method, trouble, vacanciesOf }) {
  const pane = paneCard({ ask, method, trouble });
  const vacancies = sourceVacancies(pane.alive);

  return {
    get card() {
      return pane.card;
    },
    get trouble() {
      return pane.trouble;
    },
    vacancies,
    /** Перечитать одни числа: отметка отсева, вход и время обхода. */
    read: pane.read,
    /** Дочитать следующую страницу вакансий открытого источника. */
    more: (id) => vacancies.more(vacanciesOf(id)),
    /** Зайти на источник и отдать снятие — его возвращают из эффекта. */
    watch: (events, id) =>
      watchSourceCard(events, pane.alive, id, {
        forget: () => {
          pane.forget();
          vacancies.clear();
        },
        read: (one) => {
          pane.readAll(one);
          vacancies.reload(vacanciesOf(one));
        },
      }),
  };
}
