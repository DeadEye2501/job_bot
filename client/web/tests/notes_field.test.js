// Договор поля заметки с теми, кто его ставит.
//
// Поле досылает набранное на прощание, а прощание случается уже после того,
// как карточка сменила запись. Значит номер записи обязан быть запечатан при
// заведении поля, а не прочитан в миг отправки: прочитанный тогда, он будет
// уже соседский, и заметка уедет в чужую запись, затерев её.
//
// Запечатывает номер само поле — из довода `owner`. Здесь сторожат обе
// половины договора: что номер и правда передан доводом, а не спрятан в
// замыкании зовущего, и что поле заводится заново на каждую запись.

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const ROOTS = ['app', 'components'];

/** Файлы разметки, ставящие поле заметки, вместе с их содержимым. */
function usages() {
  const found = [];
  for (const root of ROOTS) {
    for (const name of readdirSync(root)) {
      if (!name.endsWith('.svelte')) continue;
      const text = readFileSync(join(root, name), 'utf8');
      let at = text.indexOf('<NotesField');
      while (at !== -1) {
        const end = text.indexOf('/>', at);
        found.push({ file: `${root}/${name}`, tag: text.slice(at, end), before: text.slice(0, at) });
        at = text.indexOf('<NotesField', end);
      }
    }
  }
  return found;
}

describe('поле заметки', () => {
  it('где-то поставлено — иначе сторожить нечего', () => {
    expect(usages().length).toBeGreaterThan(0);
  });

  it('получает номер записи доводом', () => {
    for (const use of usages()) {
      expect(use.tag, use.file).toMatch(/\sowner=\{/);
    }
  });

  it('получает запись готовой связкой, а не замыканием зовущего', () => {
    // Замыкание читало бы номер в миг отправки — то есть уже соседский.
    for (const use of usages()) {
      expect(use.tag, use.file).toMatch(/\ssave=\{\s*[A-Za-z_$][\w$]*\s*\}/);
    }
  });

  it('заводится заново на каждую запись', () => {
    // Иначе запечатанный номер протухнет: поле переживёт смену записи и
    // продолжит слать набранное к прежней.
    for (const use of usages()) {
      const opened = use.before.lastIndexOf('{#key');
      expect(opened, use.file).toBeGreaterThan(-1);
      expect(use.before.slice(opened), use.file).not.toContain('{/key}');
    }
  });
});
