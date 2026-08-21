// @vitest-environment jsdom
//
// Следствия живого пункта «в отсев»: что случается по нажатию.
//
// Проверки договора по разметке (`blacklist_menu_item.test.js`) сторожат, что
// карточки отдают пункту оба зова и что копий пункта больше нет. Само нажатие
// видно только здесь: выбор между «занести» и «убрать» пункт делает сам, по
// нынешнему положению дел, и перепутанный выбор в разметке не виден никак.

import { cleanup, render, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import BlacklistMenuItem from '../components/BlacklistMenuItem.svelte';

afterEach(cleanup);

/** Пункт с записанным за ним следом нажатий. */
function item(blocked) {
  const trail = [];
  const shown = render(BlacklistMenuItem, {
    props: {
      blocked,
      close: () => trail.push('меню закрыто'),
      onblock: () => trail.push('занесён в отсев'),
      onunblock: () => trail.push('убран из отсева'),
    },
  });
  // Искать внутри своего куска, а не по всей странице: проверка ниже поднимает
  // два пункта рядом, и общий поиск нашёл бы сразу оба.
  return { trail, button: within(shown.container).getByRole('button') };
}

describe('живой пункт «в отсев»', () => {
  it('делает ровно то, что написано на нём самом', () => {
    // Подпись и выбор зова считаются по одному условию, и перепутать его
    // можно только в одной из двух половин: тогда «Убрать из blacklist»
    // заносило бы компанию в отсев. Поэтому половины сверяются парой — по
    // отдельности каждая зелена и при перепутанном условии.
    const off = item(false);
    expect(off.button.textContent).toContain('Добавить в blacklist');
    // Значок считается по тому же условию и был третьей его половиной, не
    // сверявшейся нигде во всём дереве: перепутай её — и у отсеянной компании
    // рядом со словами «Убрать из blacklist» стоял бы знак запрета.
    expect(off.button.textContent).toContain('block');
    off.button.click();
    expect(off.trail).toContain('занесён в отсев');
    expect(off.trail).not.toContain('убран из отсева');

    const on = item(true);
    expect(on.button.textContent).toContain('Убрать из blacklist');
    expect(on.button.textContent).toContain('restart_alt');
    on.button.click();
    expect(on.trail).toContain('убран из отсева');
    expect(on.trail).not.toContain('занесён в отсев');
  });

  it('закрывает меню за собой', () => {
    // Оставшееся открытым окошко перекрывает ту самую строку, которую пункт и
    // поменял. Закрывает не сам пункт, а общий `MenuItem` под ним, — но
    // человек нажимает именно этот пункт, и следствие видно отсюда.
    const { trail, button } = item(false);

    button.click();

    expect(trail).toContain('меню закрыто');
  });
});
