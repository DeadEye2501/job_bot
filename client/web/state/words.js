// Слова, согласованные с числами.

/** Слово, согласованное с числом.
 *
 * «1 категории» человек читает как опечатку и перестаёт верить остальному на
 * экране. Числа 11–14 — исключение русского счёта и берут последнюю форму.
 */
export function plural(count, one, few, many) {
  const tens = count % 100;
  if (tens >= 11 && tens <= 14) return many;
  const last = count % 10;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

/** Счёт вакансий при человеке, компании, кандидате в окне выбора. */
export function vacancyCount(count) {
  return `${count} ${plural(count, 'вакансия', 'вакансии', 'вакансий')}`;
}
