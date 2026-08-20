// Чёрный список, переведённый в то, что видно: роды, счёт, отбор, подсказчик.
//
// Чистые функции: строки моста приходят доводами, наружу уходят строки и
// списки. Ни моста, ни разметки этот файл не знает.

/** Роды строк отсева. Первый — общий: в нём экран открывается.
 *
 * Порядок несущий: слова стоят перед предметами, потому что ими отсев и
 * пользуются чаще всего — по одному слову отсеивается больше объявлений, чем по
 * всем каналам вместе.
 */
export const BLACKLIST_KINDS = [
  { key: '', label: 'Все' },
  { key: 'keyword', label: 'Ключевые слова' },
  { key: 'hr', label: 'HR' },
  { key: 'company', label: 'Компании' },
  { key: 'channel', label: 'Каналы' },
];

// Чего ждут в поле значения у каждого рода. Слово набирают руками, остальное
// подсказывается из уже заведённого. `none` — чем назван пустой подсказчик:
// родом, а не его кодом, и в том падеже, в каком он встаёт во фразу.
const VALUE_FIELDS = {
  keyword: {
    placeholder: 'Что блокировать (фрагмент текста вакансии)',
    hints: false,
    none: 'записей',
  },
  hr: { placeholder: '@username HR или имя', hints: true, none: 'HR' },
  company: { placeholder: 'Название компании', hints: true, none: 'компаний' },
  channel: { placeholder: '@username канала или название', hints: true, none: 'каналов' },
};

/** Чего ждёт поле значения при этом роде.
 *
 * Одна подсказка на все роды заставляла бы гадать, ждут тут ник, имя или кусок
 * текста объявления. Слово — свободный набор, и подсказывать в нём нечего:
 * предлагать существующие можно только там, где они есть.
 */
export function valueField(kind) {
  return VALUE_FIELDS[kind] ?? VALUE_FIELDS.keyword;
}

/** Сколько строк за каждой пилюлей рода.
 *
 * Без чисел пустой род нажимают и получают пустой список, не понимая, отбор это
 * или строк такого рода нет вовсе.
 */
export function blacklistCounts(rows) {
  const counts = { all: rows.length };
  for (const one of BLACKLIST_KINDS) {
    if (one.key) counts[one.key] = 0;
  }
  for (const row of rows) {
    if (counts[row.kind] !== undefined) counts[row.kind] += 1;
  }
  return counts;
}

/** Что показать подсказчиком существующих записей — и почему там пусто.
 *
 * Уже заведённые не предлагаются: мост такую строку всё равно отобьёт как
 * повтор, а человек до отказа считал бы, что заносит новую. Сравнение идёт по
 * значению и без учёта регистра — по нему же мост и сводит повторы.
 *
 * Пустот четыре, и они разные: перечень ещё не приехал, заводить нечего, всё
 * уже заведено, ничего не нашлось по набранному, — чинятся они по-разному, и
 * говорить о них одним словом значило бы посылать человека не туда. Пустота
 * вместо перечня — это «ещё не приехал»: пустой ответ моста приходит списком.
 */
export function blacklistHints({ items, rows, kind, typed }) {
  if (items === null) return { options: [], empty: 'Загрузка…' };
  const taken = new Set(
    rows.filter((one) => one.kind === kind).map((one) => one.value.toLowerCase()),
  );
  const free = items.filter((one) => !taken.has(one.value.toLowerCase()));
  const needle = typed.trim().toLowerCase();
  const options = needle
    ? free.filter((one) => `${one.label} ${one.value}`.toLowerCase().includes(needle))
    : free;
  return { options, empty: options.length ? '' : emptyHint(kind, items, free) };
}

function emptyHint(kind, items, free) {
  if (items.length === 0) return `Нет существующих ${valueField(kind).none}`;
  return free.length === 0 ? 'Все уже в blacklist' : 'Ничего не найдено';
}

/** Что сказать человеку о занесении в отсев.
 *
 * Исходов три, и различают их два поля ответа: `existed` говорит, что запись
 * уже была, `was_inactive` — что она лежала погашенной. Новости это разные:
 * «отсев начался», «отсев снова работает» и «ничего не изменилось», и по ним
 * человек решает, дописывать ли причину.
 *
 * Слова общие на три карточки: человека, компанию и канал. У компании они в
 * женском роде — «занесён» про неё читается как опечатка, — и это всё, чем
 * карточки тут различаются; написанные порознь, они разошлись бы и остальным.
 */
export function blockNote(done, female = false) {
  if (done.existed && !done.was_inactive) return `Уже в отсеве: ${done.value}`;
  // Слово целиком, а не окончанием: женский род гасит «ё» — «занесёна» вместо
  // «занесена».
  const returned = female ? 'Возвращена' : 'Возвращён';
  const added = female ? 'Занесена' : 'Занесён';
  return `${done.was_inactive ? returned : added} в отсев: ${done.value}`;
}

/** Что сказать человеку о снятии отсева.
 *
 * Снятое и то, чего не было, названы по-разному: нажатие на записи, которой
 * нет, иначе выглядит сделавшим работу.
 */
export function unblockNote(done, female = false) {
  if (done.updated) return female ? 'Убрана из отсева' : 'Убран из отсева';
  return `В отсеве ${female ? 'её' : 'его'} не было`;
}

/** Строки отсева, прошедшие род и поиск.
 *
 * Поиск идёт и по значению, и по причине: причину пишут словами, и по ней
 * вспоминают, за что строка заведена. Регистр не различается — человек
 * набирает как придётся, а значения приходят как записаны.
 */
export function blacklistShown(rows, { kind, search }) {
  const needle = search.trim().toLowerCase();
  return rows.filter((one) => {
    if (kind && one.kind !== kind) return false;
    if (!needle) return true;
    return `${one.value} ${one.reason || ''}`.toLowerCase().includes(needle);
  });
}
