// Договор пункта «в отсев» с карточками, которые его ставят.
//
// Пункт стоял тремя дословными копиями — в карточках канала, компании и
// человека, — и различались они только именем зова. Теперь он один, а
// карточка передаёт ему своё: положение дел и что делать по нажатию.
//
// Сторожатся обе половины: что копий больше нет и что каждая постановка
// отдаёт пункту свой зов, а не полагается на его догадку.

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const ROOTS = ['app', 'components'];
const HOME = 'components/BlacklistMenuItem.svelte';

/** Файлы разметки вместе с содержимым. */
function markup() {
  const found = [];
  for (const root of ROOTS) {
    for (const name of readdirSync(root)) {
      if (!name.endsWith('.svelte')) continue;
      found.push({ file: `${root}/${name}`, text: readFileSync(join(root, name), 'utf8') });
    }
  }
  return found;
}

/** Постановки пункта: файл и сам тег. */
function usages() {
  const found = [];
  for (const { file, text } of markup()) {
    let at = text.indexOf('<BlacklistMenuItem');
    while (at !== -1) {
      const end = text.indexOf('/>', at);
      found.push({ file, tag: text.slice(at, end) });
      at = text.indexOf('<BlacklistMenuItem', end);
    }
  }
  return found;
}

describe('пункт «в отсев»', () => {
  it('стоит не в одной карточке — иначе выносить было незачем', () => {
    const cards = new Set(usages().map((use) => use.file));
    expect(cards.size).toBeGreaterThan(1);
  });

  it('нигде не нарисован заново', () => {
    // Слова пункта ищутся строкой целиком: те же слова стоят подписью у
    // кнопки на вкладке отсева, и она к меню карточек отношения не имеет.
    // Сам пункт пропускается: у него эти слова стоять и должны.
    for (const { file, text } of markup()) {
      if (file === HOME) continue;
      expect(text, file).not.toMatch(/^\s*Добавить в blacklist\s*$/m);
      expect(text, file).not.toMatch(/^\s*Убрать из blacklist\s*$/m);
    }
  });

  it('получает положение дел доводом', () => {
    // Иначе пункт полез бы за ним в карточку, а знание во фронте
    // одностороннее: вниз доводами, наверх никак.
    for (const use of usages()) {
      expect(use.tag, use.file).toMatch(/\sblocked=\{/);
    }
  });

  it('получает оба зова и закрывающий зов меню', () => {
    // Оба, а не подходящий: выбор между ними и есть то, что вынесено. Отдай
    // карточка один, выбор вернулся бы в неё — в каждую свой копией.
    // Закрывающий зов затем, что оставшееся открытым окошко перекрывает ту
    // самую строку, которую пункт и поменял.
    for (const use of usages()) {
      expect(use.tag, use.file).toMatch(/\sonblock=\{/);
      expect(use.tag, use.file).toMatch(/\sonunblock=\{/);
      expect(use.tag, use.file).toMatch(/\s(close=\{|\{close\})/);
    }
  });
});
