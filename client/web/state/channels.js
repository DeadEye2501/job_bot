// Каналы, переведённые в то, что видно: имя, числа, переключатели, запоры.
//
// Чистые функции: строки моста приходят доводами, наружу уходят строки и
// признаки. Ни моста, ни разметки этот файл не знает.

// Чем назван канал, которого назвать нечем.
const UNNAMED = '— без названия —';

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

/** Числа канала: доли словом и признак того, что считать ещё нечего.
 *
 * Пустая статистика названа словами, а не нулями в столбиках: ноль читается
 * как «собрали и ничего не нашли», а канал, который ещё не обходили, об этом и
 * должен сказать.
 *
 * Доля, которой нет, — прочерк, а не ноль: у канала без откликов доля ответов
 * не нулевая, её просто не из чего считать.
 */
export function channelStats(stats) {
  return {
    empty: !stats.total,
    fit: share(stats.fit_percent),
    apply: share(stats.apply_percent),
    response: share(stats.response_percent),
  };
}

/** Переключатель опроса в строке канала.
 *
 * Канал из отсева заперт выключенным, каким бы он ни лежал в базе: обход всё
 * равно его пропустит, и включённый переключатель обещал бы работу, которой не
 * будет. Приглушены обе причины молчания — и отсев, и снятый опрос: рабочим
 * канал в обоих случаях не выглядит.
 *
 * Подпись только у запертого: у остальных она объясняла бы то, что и так видно
 * по положению переключателя.
 */
export function channelToggle(channel) {
  return {
    checked: channel.is_active && !channel.is_blacklisted,
    disabled: channel.is_blacklisted,
    dim: !channel.is_active || channel.is_blacklisted,
    title: channel.is_blacklisted ? 'В blacklist — снимите запись, чтобы включить' : '',
  };
}

/** Общий переключатель над списком каналов.
 *
 * Отсеянные в счёт не идут: их не трогает ни обход, ни это нажатие, — и
 * считай их выключенными, общий переключатель никогда не сошёлся бы с тем, что
 * видно в строках. Список из одних отсеянных запирается: включать в нём нечего.
 */
export function channelsToggle(channels) {
  const free = channels.filter((one) => !one.is_blacklisted);
  const all = free.length > 0 && free.every((one) => one.is_active);
  return { checked: all, disabled: free.length === 0, title: toggleAllTitle(channels, free, all) };
}

function toggleAllTitle(channels, free, all) {
  if (channels.length === 0) return 'Пока нет каналов';
  if (free.length === 0) return 'Все каналы в blacklist';
  return all ? 'Выключить все каналы' : 'Включить все каналы';
}

function share(percent) {
  return percent === null || percent === undefined ? '—' : `${percent}%`;
}
