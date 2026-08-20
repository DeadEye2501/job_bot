// Ходок по разметке фронта: кто и где поставил названный тег.
//
// Договоры компонентов сторожат двое — поле заметки и пункт «в отсев», — и
// обоим нужно одно: найти все постановки своего тега и посмотреть, что им
// передали. Написанные порознь, оба ходока несли один и тот же дефект среза.

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const ROOTS = ['app', 'components'];

/** Файлы разметки вместе с содержимым. */
export function markup() {
  const found = [];
  for (const root of ROOTS) {
    for (const name of readdirSync(root)) {
      if (!name.endsWith('.svelte')) continue;
      found.push({ file: `${root}/${name}`, text: readFileSync(join(root, name), 'utf8') });
    }
  }
  return found;
}

/** Конец открывающего тега: место его собственного `>`.
 *
 *  Считать до первого `>` нельзя — доводы сплошь со стрелками, и он попал бы
 *  в середину `() => …`; искать `/>` тоже нельзя — у тега с детьми его нет
 *  вовсе, и находились закрывающие знаки постороннего тега ниже по файлу.
 *  Поэтому знаки считаются: внутри фигурных скобок и внутри кавычек `>` не
 *  свой.
 */
function tagEnd(text, at) {
  let depth = 0;
  let quote = null;
  for (let i = at; i < text.length; i += 1) {
    const ch = text[i];
    if (quote) {
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") quote = ch;
    else if (ch === '{') depth += 1;
    else if (ch === '}') depth -= 1;
    else if (ch === '>' && depth === 0) return i;
  }
  return -1;
}

/** Постановки тега в одном куске разметки: сам тег и текст до него.
 *
 *  Тег с детьми ходоку не по зубам, и он говорит об этом словами: молчаливый
 *  разбор уводил всё до следующего тега из-под сторожа, а не найдя конца
 *  вовсе — в бесконечный круг, который сроку теста не прервать, потому что
 *  он синхронный.
 */
export function placementsIn(text, tag, where = 'разметка') {
  const found = [];
  let at = text.indexOf(tag);
  while (at !== -1) {
    const end = tagEnd(text, at);
    if (end === -1) throw new Error(`${where}: тег ${tag} не закрыт`);
    const written = text.slice(at, end);
    // Однофамилец: `<NotesFieldGroup` начинается с `<NotesField`, и без этой
    // проверки договор поля сторожился бы на обёртке вокруг него.
    if (/^[\s/]/.test(text[at + tag.length])) {
      if (!written.trimEnd().endsWith('/')) {
        throw new Error(`${where}: тег ${tag} применён с детьми, ходок такого не разбирает`);
      }
      found.push({ tag: written.slice(0, written.lastIndexOf('/')), before: text.slice(0, at) });
    }
    at = text.indexOf(tag, end);
  }
  return found;
}

/** Постановки названного тега по всей разметке: файл, сам тег и текст до него. */
export function placed(tag) {
  return markup().flatMap(({ file, text }) =>
    placementsIn(text, tag, file).map((one) => ({ file, ...one })),
  );
}
