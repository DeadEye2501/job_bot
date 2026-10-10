// Идёт ли прогон — общее для всего окна.
//
// Знать это нужно не одной нижней полосе: пока идёт обход, заперты и кнопки
// экранов, которые запускают конвейер или агента. Учёт один, иначе полоса и
// экран разошлись бы — одна показывала бы ход, а другой пускал бы второй прогон.
//
// Вести о начале и конце прогона и об ожидании человека слушает только этот
// файл; остальные читают `round.running` и `round.human` или просят позвать их
// в миг начала или конца (`round.onStart`, `round.onFinish`).

let running = $state(false);
let human = $state(null);
const starters = new Set();
const finishers = new Set();

/** Что известно о прогоне сейчас. */
export const round = {
  /** Идёт ли прогон: обход, прогон одного источника, вход или разбор. */
  get running() {
    return running;
  },

  /** Кого ждёт прогон: `{ kind, host }` — капча или вход на сайт, — или пусто. */
  get human() {
    return human;
  },

  /** Позвать в миг начала прогона; отдаёт отписку.
   *
   * Зов синхронный, а не эффектом по `running`: весть о начале и первая весть
   * хода приходят одной пачкой, и сброс, отложенный до эффекта, стёр бы уже
   * пришедший ход.
   */
  onStart(hear) {
    starters.add(hear);
    return () => starters.delete(hear);
  },

  /** Позвать в миг конца шедшего прогона; отдаёт отписку.
   *
   * По переходу «шёл → кончился», а не по каждому «не идёт»: экран, читающий
   * итог прогона, перечитывал бы себя ещё и при каждом открытии окна.
   */
  onFinish(hear) {
    finishers.add(hear);
    return () => finishers.delete(hear);
  },
};

/** Подписать учёт на вести моста; отдаёт отписку.
 *
 * Подписка начинает с «не идёт»: окно открывается заново, а прогон, шедший до
 * этого, о себе уже не напомнит — его конец ушёл в прошлое окно.
 */
export function hearRound(events) {
  running = false;
  human = null;
  const offs = [
    events.on('ingestion_started', () => {
      running = true;
      starters.forEach((hear) => hear());
    }),
    // Ожидание кончается и с концом прогона: остановленный обход отпускает
    // агента молча, вести «человек справился» за ним не будет.
    events.on('ingestion_finished', () => {
      const was = running;
      running = false;
      human = null;
      if (was) finishers.forEach((hear) => hear());
    }),
    events.on('human_needed', (need) => {
      human = need;
    }),
    events.on('human_resolved', () => {
      human = null;
    }),
  ];
  return () => offs.forEach((off) => off());
}
