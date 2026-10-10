// Навыки анкеты, разложенные так, как их читает человек.
//
// Чистые функции: перечень приходит доводом, наружу уходят группы, доли и
// слова. Ни моста, ни разметки этот файл не знает.

import { fillPercent } from './chosen.js';
import { matching } from './search.js';
import { counted } from './words.js';

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

/** Раскладка, в которой остались навыки, попавшие под набранное.
 *
 * Пустая категория уходит целиком: подпись без строк под ней читается как
 * «навык потерян», а не как «здесь не нашлось».
 *
 * Просеивание живёт здесь, а не у подборщика: показывать переданное — вся его
 * работа, а знание о том, чем навыки различают, принадлежит этому файлу.
 */
export function groupsMatching(skills, typed) {
  return grouped(skills)
    .map((group) => ({
      name: group.name,
      items: matching(group.items, typed, (one) => one.name),
    }))
    .filter((group) => group.items.length > 0);
}

/** Какую долю дорожки залить под этот уровень. */
export function levelPercent(level) {
  return fillPercent(level, TOP_LEVEL);
}

/** Счёт в заголовке вкладки: сколько всего навыков и категорий.
 *
 * Навыки не склоняются: их число меняется на каждой правке строки, и слово
 * дёргалось бы под курсором. У категорий оно стоит месяцами.
 */
export function countNote(skills, categories) {
  return (
    `${skills} навыков, ` +
    counted(categories, 'категория', 'категории', 'категорий')
  );
}

/** Каким станет перечень синонимов, когда набор закончили.
 *
 * Отменённый набор перечня не трогает: запись отложенная, и опечатка иначе
 * успевает уехать в базу. Повтор без учёта регистра тоже не встаёт — мост
 * сверяет написания так же, и пара значила бы лишнюю строку, которая ничего
 * не находит.
 */
export function aliasesAfter(aliases, typed, keep) {
  const value = typed.trim();
  if (!keep || !value) return aliases;
  const same = aliases.some((one) => one.trim().toLowerCase() === value.toLowerCase());
  return same ? aliases : [...aliases, value];
}
