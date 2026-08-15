// Месяц, разложенный по неделям: то, что видно в сетке календаря.
//
// Своим модулем, а не в `dates.js`: тот про одну дату — как её набирают и
// какой её понимает мост, — а здесь перебирают дни месяца и ходят по нему
// вперёд и назад.

/** Дни недели с понедельника. Порядок несущий: по нему считается, в какую
 *  колонку встаёт первое число месяца. */
export const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

const MONTHS = [
  'Январь',
  'Февраль',
  'Март',
  'Апрель',
  'Май',
  'Июнь',
  'Июль',
  'Август',
  'Сентябрь',
  'Октябрь',
  'Ноябрь',
  'Декабрь',
];

const WEEK = WEEKDAYS.length;

// Сколько пустых клеток стоит перед первым числом. Часы считают неделю с
// воскресенья, а читают её с понедельника.
function indent(year, month) {
  const first = new Date(year, month - 1, 1).getDay();
  return (first + WEEK - 1) % WEEK;
}

/** Дни месяца, разложенные по неделям. Пустая клетка — `null`.
 *
 * Недели ровно по семь клеток: числа стоят колонками под подписями дней, и
 * короткая неделя сдвинула бы всё, что под ней.
 */
export function monthGrid(year, month) {
  const length = new Date(year, month, 0).getDate();
  const cells = [
    ...Array.from({ length: indent(year, month) }, () => null),
    ...Array.from({ length }, (_, at) => at + 1),
  ];
  while (cells.length % WEEK !== 0) cells.push(null);
  const weeks = [];
  for (let at = 0; at < cells.length; at += WEEK) weeks.push(cells.slice(at, at + WEEK));
  return weeks;
}

/** Чем подписан показанный месяц. */
export function monthTitle(year, month) {
  return `${MONTHS[month - 1]} ${year}`;
}

/** Соседний месяц. Край года часы переваливают сами: тринадцатый месяц — это
 *  январь следующего, и считать его отдельно значило бы считать дважды. */
export function shiftMonth(year, month, step) {
  const at = new Date(year, month - 1 + step, 1);
  return { year: at.getFullYear(), month: at.getMonth() + 1 };
}
