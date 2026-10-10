// Каналы, переведённые в то, что видно: имя, числа, переключатели, запоры.
//
// Чистые функции: строки моста приходят доводами, наружу уходят строки и
// признаки. Ни моста, ни разметки этот файл не знает.

import { BLOCKED_TITLE, sourceToggle } from './sources.js';
import { UNNAMED } from './unnamed.js';

/** Чем подписать канал в списке.
 *
 * Название — сверху, ник — под ним: по названию канал узнают, по нику ищут.
 * Названия у канала может не быть — тогда его место занимает ник, а совсем
 * безымянный назван номером: показать нечего, но строка должна остаться
 * нажимаемой.
 */
export function channelName(channel) {
  const handle = channel.username ? `@${channel.username}` : '';
  if (channel.title) return { name: channel.title, handle };
  if (channel.username) return { name: `@${channel.username}`, handle: '' };
  return { name: `Канал #${channel.id}`, handle: '' };
}

/** Чем подписан канал в строке списка: подпись и настоящее ли это название.
 *
 * Совсем безымянный назван прочерком, а не номером: номером его зовёт шапка
 * карточки — там подпись обязана быть, — а в списке «Канал #42» встал бы в ряд
 * названий и читался бы как название. По второму ответу подпись глушат серым.
 */
export function channelTitle(channel) {
  const named = Boolean(channel.title || channel.username);
  return { name: named ? channelName(channel).name : UNNAMED, named };
}

/** Чем заперт ручной прогон канала; пусто — прогонять можно.
 *
 * Отсев старше неживых ламп: лампа погаснет и зажжётся сама, а канал в чёрном
 * списке заносили туда затем, чтобы он больше не приносил вакансий. Ручной
 * прогон принёс бы их в обход отметки — отсев по тексту тут не спасает, он
 * сверяет текст поста, а написание канала это `@ник`.
 *
 * Пока карточка не прочитана, запирает только лампа: чем окажется канал, ещё
 * неизвестно, а меню в это время не нарисовано.
 */
export function pollBlock(card, lockedTip) {
  if (card?.blacklist_value) return 'Канал в чёрном списке — прогнать его нельзя';
  return lockedTip;
}

/** Переключатель опроса в строке канала; `enabled` — общий выключатель каналов.
 *
 * Заперт у канала один — отсев (`sources.sourceToggle`).
 */
export function channelToggle(channel, enabled) {
  return sourceToggle(
    { active: channel.is_active, open: !channel.is_blacklisted, lockTitle: BLOCKED_TITLE },
    enabled,
  );
}
