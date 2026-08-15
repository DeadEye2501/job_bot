// Списки контактов, переведённые в то, что видно: имена, отбор, отметки.
//
// Чистые функции: строки моста приходят доводами, наружу уходят строки и
// списки. Ни моста, ни разметки этот файл не знает.

/** Роды строк отсева. Первый — общий: в нём экран открывается. */
export const BLACKLIST_KINDS = [
  { key: '', label: 'Все' },
  { key: 'hr', label: 'Люди' },
  { key: 'company', label: 'Компании' },
  { key: 'channel', label: 'Каналы' },
  { key: 'keyword', label: 'Слова' },
];

/** Чем подписать канал в списке.
 *
 * Название — сверху, ник — под ним: по названию канал узнают, по нику ищут.
 * Названия у канала может не быть — тогда его место занимает ник, а совсем
 * безымянный назван номером: показать нечего, но строка должна остаться
 * нажимаемой.
 */
export function channelName(channel) {
  if (channel.title) return { name: channel.title, handle: `@${channel.username}` };
  if (channel.username) return { name: `@${channel.username}`, handle: '' };
  return { name: `Канал #${channel.id}`, handle: '' };
}

/** Адрес, по которому человека или канал открывают в самом Telegram.
 *
 * Ник, а не номер учётной записи: по номеру Telegram открывает разговор только
 * своим клиентом и не всегда, а ник работает и в окне браузера.
 */
export function telegramHref(username) {
  return `https://t.me/${username}`;
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

/** Как назвать человека в чужой карточке.
 *
 * Имя приходит из переписки и бывает пустым, ник есть почти всегда — по нему
 * человека и узнают в самом Telegram. Нет ни того ни другого (учётная запись
 * скрыла ник) — остаётся номер: строка должна читаться, а не пустовать.
 */
export function personName(person) {
  if (person.name) return person.name;
  if (person.telegram_username) return `@${person.telegram_username}`;
  return `Человек #${person.id}`;
}

/** Буквы имени на месте снимка.
 *
 * Снимок есть не у всех: у заведённых руками его нет вовсе, а пустой кружок
 * читается как недогрузившаяся картинка. Берутся первое слово и последнее —
 * имя и фамилия; отчество между ними ничего не различает.
 */
export function initials(name) {
  const words = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '';
  const first = words[0][0];
  const last = words.length === 1 ? '' : words[words.length - 1][0];
  return `${first}${last}`.toUpperCase();
}

/** Чем подписана строка списка непрочитанных переписок.
 *
 * Ник под именем стоит только тогда, когда есть и то и другое: сам по себе он
 * уже стоит на месте имени, и повторённый ниже занимал бы строку впустую.
 *
 * Безымянный назван здесь «HR #N», а не так, как зовёт его карточка: списком
 * над полосой человек выбирает, кому ответить, и слово это пришло из образца
 * (main.html 15246–15256).
 */
export function unreadLine(row) {
  const handle = row.telegram_username ? `@${row.telegram_username}` : '';
  const name = (row.name || '').trim();
  return {
    name: name || handle || `HR #${row.hr_id}`,
    sub: name && handle ? handle : '',
  };
}

/** Есть ли чем назвать человека, которого заводят руками.
 *
 * Хоть что-нибудь из трёх: имя, ник или номер учётной записи. Карточка,
 * названная одними заметками, не находится потом ни поиском, ни отправкой —
 * заметки не ссылаются на человека ничем, — и удалять её пришлось бы руками.
 * То же правило держит и мост (`client/form_payloads.hr_is_identified`); здесь
 * оно стоит затем, чтобы окно не отправляло заведомо отказной вопрос.
 */
export function named(draft) {
  return Boolean(
    draft.name.trim() || draft.telegram_username.trim() || draft.telegram_user_id.trim(),
  );
}

/** Чем подписать человека в списке.
 *
 * Имя — сверху, ник и компания — под ним. Тёзок в переписке хватает: различают
 * их по нику, а вспоминают по компании, из которой человек писал последний
 * раз. Обе половины называются всегда: пустое место читалось бы как
 * недогрузившаяся строка, а «без ника» тут говорящее — такого человека не
 * найти в Telegram по имени, и вспоминать его придётся по компании.
 */
export function personLine(person) {
  const handle = person.telegram_username ? `@${person.telegram_username}` : 'без ника';
  return {
    name: personName(person),
    sub: `${handle} · ${person.last_company_name || 'без компании'}`,
  };
}

/** Человек в том виде, в каком его показывает окно выбора.
 *
 * Подпись берётся тем же правилом, что и в списке: один и тот же человек,
 * названный в двух местах по-разному, читается как двое разных. Снимка может
 * не быть вовсе — тогда кружок сам поставит на его место буквы имени.
 */
export function personCandidate(person) {
  return {
    id: person.id,
    icon: 'person',
    avatar: person.avatar ?? null,
    ...personLine(person),
    count: person.vacancy_count,
    blocked: person.is_blacklisted,
  };
}

/** Строки отсева, прошедшие род и поиск.
 *
 * Поиск идёт и по значению, и по причине: причину пишут словами, и по ней
 * вспоминают, за что строка заведена. Регистр не различается — человек
 * набирает как придётся, а значения приходят как записаны.
 */
export function blacklistShown(rows, { kind, search }) {
  const needle = search.trim().toLowerCase();
  return rows.filter((one) => {
    if (kind && one.kind !== kind) return false;
    if (!needle) return true;
    return `${one.value} ${one.reason || ''}`.toLowerCase().includes(needle);
  });
}

/** Отперта ли кнопка «Связать».
 *
 * Промах мышью по строке списка не должен менять привязку: выбор строки только
 * помечает её, а связывает отдельная кнопка. Выбор уже привязанного кнопку не
 * отпирает — нажатие переписало бы связь тем же значением и записало в ленту
 * перемену, которой не было.
 */
export function linkReady({ current, chosen }) {
  return chosen !== null && chosen !== undefined && chosen !== current;
}

/** Годится ли пришедший ответ: он должен отвечать на последний вопрос.
 *
 * Человек набирает поиск посимвольно, и ответы возвращаются вразнобой: ляг
 * первый поверх третьего — в списке оказались бы строки, которых он уже не
 * ищет.
 */
export function fresher(answered, asked) {
  return answered === asked;
}
