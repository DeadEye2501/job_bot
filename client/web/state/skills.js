// Навыки анкеты, разложенные так, как их читает человек.
//
// Чистые функции: перечень приходит доводом, наружу уходят группы, доли и
// слова. Ни моста, ни разметки этот файл не знает.

import { fillPercent } from './chosen.js';
import { plural } from './words.js';

const NO_CATEGORY = 'Общее';

/** Наибольший уровень навыка. Дорожка ползунка размечена по нему. */
const TOP_LEVEL = 10;

/** Навыки, разложенные по категориям.
 *
 * Порядок категорий — по первому появлению в перечне, а не по алфавиту:
 * человек расставил их сам, и пересортировка рассыпала бы его раскладку при
 * каждом открытии вкладки.
 *
 * Навык без категории попадает в общую: пустая подпись читалась бы как
 * поломка списка, а приходит такой навык сплошь и рядом — из разбора резюме.
 */
export function grouped(skills) {
  const groups = [];
  const seen = new Map();
  for (const skill of skills) {
    const name = skill.category || NO_CATEGORY;
    if (!seen.has(name)) {
      seen.set(name, groups.length);
      groups.push({ name, items: [] });
    }
    groups[seen.get(name)].items.push(skill);
  }
  return groups;
}

/** Какую долю дорожки залить под этот уровень. */
export function levelPercent(level) {
  return fillPercent(level, TOP_LEVEL);
}

/** Счёт в заголовке вкладки: сколько всего навыков и категорий. */
export function countNote(skills, categories) {
  return (
    `${skills} ${plural(skills, 'навык', 'навыка', 'навыков')}, ` +
    `${categories} ${plural(categories, 'категория', 'категории', 'категорий')}`
  );
}
