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

/** Годится ли пришедший ответ: он должен отвечать на последний вопрос.
 *
 * Человек набирает поиск посимвольно, и ответы возвращаются вразнобой: ляг
 * первый поверх третьего — в списке оказались бы строки, которых он уже не
 * ищет.
 */
export function fresher(answered, asked) {
  return answered === asked;
}
