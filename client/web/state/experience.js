// Места работы, переведённые в то, что видно и что набирают.
//
// Чистые функции: строка опыта приходит доводом, наружу уходят строки.
// Ни моста, ни разметки этот файл не знает.

const DMY = /^(\d{2})\.(\d{2})\.(\d{4})$/;

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

/** Период работы для шапки карточки.
 *
 * Месяц и год без дня: места работы различают по месяцам, а день удлиняет
 * строку вдвое. Открытый конец назван словами — по нему и читают, работает
 * человек здесь сейчас или нет.
 */
export function period(startIso, endIso) {
  if (!startIso) return '';
  const short = (iso) => {
    const [year, month] = iso.split('-');
    return `${month}.${year}`;
  };
  return `${short(startIso)} — ${endIso ? short(endIso) : 'настоящее время'}`;
}

/** Чем подписана свёрнутая карточка.
 *
 * Карточки свёрнуты, и это всё, по чему человек их различает; безымянная
 * названа прямо, иначе её не отличить от пустого места в списке.
 */
export function cardTitle(exp) {
  return {
    company: exp.company || 'Без названия',
    role: exp.role || '',
    period: period(exp.start_date, exp.end_date),
  };
}
