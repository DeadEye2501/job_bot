// Окно заведения над списком: отказ остаётся в окне, удача говорит словом по
// ответу моста и перечитывает список им же.

import { describe, expect, it } from 'vitest';

import { contactAdding } from '$state/contact_adding.svelte.js';

import { held } from './bridge_stub.js';

// Окно об одном поле — адрес канала, сайта или контакт: черновик строкой.
const ADDRESS = {
  blank: () => '',
  named: (draft) => Boolean(draft.trim()),
  // Слово строится и из набранного: так видно, что его спросили до закрытия
  // окна, — закрытие черновик чистит.
  done: (draft, answer) => `Добавлено: ${draft} → ${answer.name}`,
};

function adding(save, form = ADDRESS) {
  const said = [];
  const again = [];
  const entry = contactAdding({
    list: { again: (answer) => again.push(answer) },
    form,
    save,
    say: (text) => said.push(text),
  });
  return { entry, said, again };
}

describe('окно заведения над списком', () => {
  it('отказ моста остаётся строкой в окне, а окно — открытым', async () => {
    // Отказ здесь почти всегда опечатка в набранном: объясняют её там же,
    // где набирали, и набранное человеку ещё пригодится.
    const { entry, said } = adding(async () => {
      throw new Error('Адрес не похож на сайт');
    });
    entry.adding = true;
    entry.draft = 'не сайт';

    await entry.create();

    expect(entry.trouble).toBe('Адрес не похож на сайт');
    expect(entry.adding).toBe(true);
    expect(said).toEqual([]);
  });

  it('закрытое окно забывает и набранное, и отказ', async () => {
    const { entry } = adding(async () => {
      throw new Error('отказ');
    });
    entry.adding = true;
    entry.draft = 'x';
    await entry.create();

    entry.adding = false;

    expect([entry.draft, entry.trouble]).toEqual(['', '']);
  });

  it('удача говорит словом по ответу моста и отдаёт ответ списку', async () => {
    const answer = { name: 'Пример' };
    const { entry, said, again } = adding(async () => answer);
    entry.adding = true;
    entry.draft = 'example.test';

    await entry.create();

    expect(said).toEqual(['Добавлено: example.test → Пример']);
    expect(again).toEqual([answer]);
    expect(entry.adding).toBe(false);
  });

  it('отказ, уже показанный плашкой, окно не закрывает и списка не трогает', async () => {
    const { entry, said, again } = adding(async () => null);
    entry.adding = true;
    entry.draft = 'example.test';

    await entry.create();

    expect(entry.adding).toBe(true);
    expect(entry.draft).toBe('example.test');
    expect([said, again]).toEqual([[], []]);
  });

  it('после отказа кнопка окна снова открыта', async () => {
    const { entry } = adding(async () => {
      throw new Error('отказ');
    });
    entry.adding = true;
    entry.draft = 'x';

    await entry.create();

    expect(entry.saving).toBe(false);
  });

  it('пустое не уходит на мост, и второе нажатие, пока летит первое, тоже', async () => {
    let sent = 0;
    const answer = held();
    const { entry } = adding(() => {
      sent += 1;
      return answer.promise;
    });
    entry.adding = true;
    entry.draft = '   ';
    await entry.create();
    expect(sent).toBe(0);

    entry.draft = 'example.test';
    const first = entry.create();
    await entry.create();
    answer.give({ name: 'Пример' });
    await first;

    expect(sent).toBe(1);
  });

  it('пустое слово формы не говорит ничего, а список всё равно перечитан', async () => {
    const quiet = { ...ADDRESS, done: () => '' };
    const { entry, said, again } = adding(async () => ({ name: 'Пример' }), quiet);
    entry.adding = true;
    entry.draft = 'x';

    await entry.create();

    expect(said).toEqual([]);
    expect(again).toHaveLength(1);
  });
});
