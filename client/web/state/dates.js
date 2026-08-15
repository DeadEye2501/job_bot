// Дата в двух её видах: набранная человеком и понятная мосту.
//
// Своим модулем, а не в опыте работы: даты набирают в двух разных предметах —
// период работы в анкете и период активности в отборе, — и модуль опыта,
// обслуживающий заодно и отбор, перестал бы описываться одной фразой.

const DMY = /^(\d{2})\.(\d{2})\.(\d{4})$/;

// Ведущий ноль. Мост разбирает ISO по знакам, и `2026-8-4` он не прочтёт.
function padded(number) {
  return String(number).padStart(2, '0');
}

/** Дата в том виде, в каком её читают и набирают.
 *
 * Мост говорит `2020-03-01`, человек — `01.03.2020`. Покажи ему первое, он
 * решил бы, что поле не его.
 */
export function showDate(iso) {
  if (!iso) return '';
  const [year, month, day] = iso.split('-');
  return year && month && day ? `${day}.${month}.${year}` : '';
}

/** Набранная дата в том виде, в каком её принимает мост.
 *
 * Недобранное не уезжает вовсе: человек набирает посимвольно, и `01.03.20` на
 * полпути — не дата, а мост записал бы двадцатый год нашей эры.
 */
export function asIso(text) {
  const parts = DMY.exec((text || '').trim());
  if (parts === null) return null;
  const [, day, month, year] = parts;
  return `${year}-${month}-${day}`;
}

/** ISO-дата, разобранная на числа.
 *
 * Числами, а не строками: календарь открывается на том месяце, что уже
 * выбран, и сравнивать «08» с восьмёркой пришлось бы в каждой клетке сетки.
 */
export function dayOf(iso) {
  const [year, month, day] = iso.split('-').map(Number);
  return { year, month, day };
}

/** Выбранный в календаре день в том виде, в каком его принимает мост. */
export function isoDay(year, month, day) {
  return `${year}-${padded(month)}-${padded(day)}`;
}

/** День и часы одной строкой, местными часами.
 *
 * Ею подписано объявление в окне исходного текста: по дню и времени пост
 * находят в самом канале, а давность словом («3 д») для поиска не годится.
 * Времени может не быть вовсе — полночь 1970 года человек прочтёт как сбой
 * часов, поэтому вместо неё пустое место.
 */
export function showStamp(iso) {
  if (!iso) return '';
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '';
  const day = `${at.getFullYear()}-${padded(at.getMonth() + 1)}-${padded(at.getDate())}`;
  return `${day} ${padded(at.getHours())}:${padded(at.getMinutes())}`;
}

/** Годна ли набранная дата: да, нет или «ещё набирают».
 *
 * Три ответа, а не два: пока в поле обрывок, оно не должно краснеть на каждом
 * знаке — красное поле при первой же цифре человек читает как отказ.
 *
 * Существование дня проверяется отдельно от её вида: часы перекатывают
 * «31.02» на март молча, и отбор пошёл бы по чужим суткам.
 */
export function validDate(text) {
  const iso = asIso(text);
  if (iso === null) return null;
  const [year, month, day] = iso.split('-').map(Number);
  const at = new Date(year, month - 1, day);
  return at.getMonth() + 1 === month && at.getDate() === day;
}
