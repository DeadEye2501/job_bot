// Нижняя полоса над подставным мостом — для проверок самой полосы и окон, которые
// она открывает.

import { render } from '@testing-library/svelte';

import BottomBar from '../app/BottomBar.svelte';
import { hearRound } from '../state/round.svelte.js';
import { answering, listening } from './bridge_stub.js';

/** Полоса со здоровьем `health`; ответ — зовы моста, подсказки запора, плашки
 *  и обработчики вестей.
 *
 *  `counts` — что по очереди отвечает число новых вакансий; последнее держится.
 *  `app` — запущенная версия и может ли копия обновиться; `updates` — что по
 *  очереди отвечает проверка обновления, последнее держится.
 */
export function bar(health, counts = [0], { app = null, updates = [{ newer: null, trouble: null }] } = {}) {
  const tips = [];
  // Плашки полоса показывает не через мост, а через `say`: отказ запертого
  // тумблера виден только здесь.
  const said = [];
  const left = [...counts];
  const checks = [...updates];
  const { asked, ask } = answering((method, payload) => {
    if (method === 'system.initial') return { unread: { count: 0 }, mode: 'Full', health };
    if (method === 'system.set_mode') return { mode: payload };
    if (method === 'system.health') return health;
    if (method === 'system.new_vacancies') return { count: left.length > 1 ? left.shift() : left[0] };
    if (method === 'system.check_update') return checks.length > 1 ? checks.shift() : checks[0];
    return {};
  });

  // Вести полосе приходят подпиской: проверка зовёт обработчики так же, как мост.
  const events = { ...listening(), run: () => {}, stop: () => {} };
  const { handlers } = events;
  // Вести о начале и конце прогона слушает общий учёт, а не полоса: в окне его
  // подписывает оболочка, здесь — проверка, на те же поддельные вести.
  hearRound(events);

  render(BottomBar, {
    props: {
      ask,
      say: (text) => said.push(text),
      events,
      onlocked: (tip) => tips.push(tip),
      oncontact: () => {},
      app,
    },
  });
  return { asked, tips, said, handlers };
}
