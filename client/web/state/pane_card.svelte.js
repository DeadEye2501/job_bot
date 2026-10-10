// Карточка правой панели: сама запись, слово о беде, её короткие списки и смена
// открытой записи.
//
// Своим объявлением, потому что карточки человека, компании, канала и
// агрегатора заходили на запись дословно одинаково: сброс показанного прежней,
// чтение карточки и её списков, отбой ответов о прежней. Своё у каждой —
// поля, меню и шапка — остаётся в ней; листаемые вакансии источника —
// в `source_card`.
//
// Имён методов моста здесь нет: они приходят доводами, чтобы стоять на шве, в
// самой карточке.

import { living } from '$state/alive.js';
import { cardRead } from '$state/card_read.js';
import { miniRead } from '$state/mini_read.js';

/** Заводит карточку правой панели.
 *
 * `method` — чтение карточки по номеру, `trouble` — слова его отказа.
 * `lists` — короткие списки карточки по имени: у каждого `method`, `payload`
 * и `key`, как у `miniRead`; пришедшее ложится в `rows` под тем же именем.
 */
export function paneCard({ ask, method, trouble: refused, lists = {} }) {
  let card = $state(null);
  let trouble = $state('');
  const rows = $state(
    Object.fromEntries(Object.keys(lists).map((name) => [name, []])),
  );

  // Свой счёт попыток на каждый вопрос: панель живёт одна на всю вкладку, и
  // запись в ней переключают нажатием по соседней строке — ответ про прежнюю,
  // лёгший поверх свежего, показал бы её числа под новым именем.
  const alive = living();

  const read = cardRead({
    ask,
    method,
    trouble: refused,
    alive: () => alive.now,
    show: (now) => ({ card, trouble } = now),
  });

  const loads = Object.entries(lists).map(([name, list]) =>
    miniRead({
      ask,
      alive: () => alive.now,
      ...list,
      show: (got) => (rows[name] = got),
    }),
  );

  /** Убрать показанное прежней записью: панель одна, и её числа под новым
   *  именем читались бы как числа новой. */
  function forget() {
    card = null;
    trouble = '';
    for (const name of Object.keys(rows)) rows[name] = [];
  }

  /** Прочитать карточку вместе с её списками. */
  function readAll(id) {
    read(id);
    for (const load of loads) load(id);
  }

  return {
    get card() {
      return card;
    },
    get trouble() {
      return trouble;
    },
    rows,
    alive,
    /** Перечитать одну карточку: после правки поля или отметки отсева. */
    read,
    forget,
    readAll,
    /** Зайти на запись и отдать снятие — его возвращают из эффекта. */
    enter: (id) =>
      alive.entered(() => {
        forget();
        readAll(id);
      }),
  };
}
