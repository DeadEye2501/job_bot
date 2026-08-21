// @vitest-environment jsdom
//
// Нижняя полоса как своя сборка.
//
// Жила она внутри оболочки — вместе с боковым меню и полем раздела, — и её
// десять состояний с десятью объявлениями делали самый большой файл фронта
// единственной точкой, которую правят и при добавлении раздела, и при любой
// правке полосы.
//
// Своей работы у полосы две, и обе видны только отсюда: часы здоровья, которые
// гасят бота, когда что-то отвалилось, и подсказка о запертых кнопках, которую
// ждут наверху — её раздают экранам.

import { cleanup, render } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import BottomBar from '../app/BottomBar.svelte';

afterEach(cleanup);

/** Дождаться, пока осядут ответы моста и отрисовка. */
async function settled() {
  for (let i = 0; i < 6; i += 1) {
    await tick();
    await new Promise((done) => setTimeout(done, 0));
  }
}

function bar(health) {
  const asked = [];
  const tips = [];
  const ask = async (method, ...args) => {
    asked.push({ method, args });
    if (method === 'system.initial') return { unread: { count: 0 }, mode: 'Full', health };
    if (method === 'system.set_mode') return { mode: args[0] };
    if (method === 'system.health') return health;
    return {};
  };

  render(BottomBar, {
    props: {
      ask,
      say: () => {},
      events: { on: () => () => {}, run: () => {}, stop: () => {} },
      onlocked: (tip) => tips.push(tip),
      oncontact: () => {},
    },
  });
  return { asked, tips };
}

describe('живая нижняя полоса', () => {
  it('гасит бота, когда что-то отвалилось, и называет наверх причину', async () => {
    // Бот, работающий против мёртвого сеанса Telegram, крутит обходы впустую, а
    // переключатель в этот миг уже заперт, и человек выключить его не может.
    const { asked, tips } = bar({ db: true, tg: false, chat: true, embed: true });
    await settled();

    expect(asked.some((one) => one.method === 'system.set_mode' && one.args[0] === 'Off')).toBe(true);
    expect(tips.at(-1)).toContain('TG');
  });

  it('при живых системах бота не трогает и подсказку отдаёт пустой', async () => {
    const { asked, tips } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    expect(asked.some((one) => one.method === 'system.set_mode')).toBe(false);
    expect(tips.at(-1)).toBe('');
  });
});
