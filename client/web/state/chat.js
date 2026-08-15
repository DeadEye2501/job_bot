// Переписка, переведённая в то, что видно: лента по дням, отметки и запреты.
//
// Чистые функции: письма моста приходят доводами, наружу уходят строки и
// списки. «Сегодня» тоже довод — без него эти функции нельзя было бы проверить,
// не подменяя часы всей странице.

// Месяцы сокращены: подпись дня делит ленту поперёк, и полное название
// растягивает эту черту на пол-ленты.
const MONTHS = [
  'янв', 'фев', 'мар', 'апр', 'мая', 'июн',
  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
];

/** Разложить письма по дням, сохранив их порядок.
 *
 * Подпись дня стоит над первым письмом этого дня, а не над каждым: иначе лента
 * превращается в чересполосицу дат.
 *
 * Письмо без времени выпадает вовсе — поставить его некуда, а под чужой
 * подписью дня оно соврало бы.
 */
export function byDays(messages, now) {
  const days = [];
  for (const one of messages) {
    if (!one.sent_at) continue;
    const at = new Date(one.sent_at);
    const key = `${at.getFullYear()}-${at.getMonth()}-${at.getDate()}`;
    const last = days[days.length - 1];
    if (last && last.key === key) last.messages.push(one);
    else days.push({ key, day: dayLabel(at, now), messages: [one] });
  }
  return days;
}

/** Чем показать вложение письма: снимком, строкой файла или ничем.
 *
 * Снимок виден прямо в ленте — по нему и понимают, что прислали, не выходя из
 * переписки. Скачивает бот не всё: у нескачанного остаётся только имя, и
 * нажимать на него нечего, а промолчать нельзя — письмо выглядело бы пустым.
 */
export function attachmentKind(message) {
  if (!message.media_kind) return '';
  if (!message.media_path) return 'gone';
  return message.media_kind === 'photo' ? 'photo' : 'file';
}

/** Часы и минуты письма. Ведущий ноль обязателен: «9:5» читается как сломанное. */
export function chatTime(sentAt) {
  const at = new Date(sentAt);
  return `${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

/** Дошло ли своё письмо до собеседника.
 *
 * Две галочки — прочитано, одна — отправлено. На чужом письме отметка означала
 * бы неизвестно что, а на удалённом — говорила бы о том, чего уже нет.
 */
export function tick(message) {
  if (message.is_incoming || message.is_deleted) return '';
  return message.read_at ? '✓✓' : '✓';
}

/** Есть ли в ленте что отмечать прочитанным.
 *
 * Своё письмо и удалённое не в счёт: отметка говорит «я прочитал», и уходит она
 * в Telegram — на своём письме она означала бы неизвестно что, а зов без повода
 * гонял бы базу на каждое открытие карточки.
 */
export function unread(messages) {
  return messages.some((one) => one.is_incoming && !one.read_at && !one.is_deleted);
}

/** Почему этому человеку нельзя написать. Пусто — значит можно.
 *
 * Заслон отсева стоит и здесь, а не только у бота: письмо, отправленное из
 * окна, ушло бы в обход его собственного правила. Адресата же берут из ника
 * или номера учётной записи, и без обоих отправка не нашла бы собеседника.
 */
export function sendBlock(card) {
  if (card.blacklist_value) {
    return `HR в blacklist (${card.blacklist_value}) — переписка отключена`;
  }
  if (!card.telegram_username?.trim() && !card.telegram_user_id) {
    return 'Невозможно отправить — нет Telegram-контакта';
  }
  return '';
}

/** Как назвать день письма: сегодняшний и вчерашний — словом, прочие — датой.
 *
 * Дату сегодняшнего письма человек читает как «когда-то»: слово говорит
 * быстрее числа. Год ставится только у прошлых лет — в этом он и так известен.
 */
function dayLabel(at, now) {
  if (sameDay(at, now)) return 'Сегодня';
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay(at, yesterday)) return 'Вчера';
  const date = `${at.getDate()} ${MONTHS[at.getMonth()]}`;
  return at.getFullYear() === now.getFullYear() ? date : `${date} ${at.getFullYear()}`;
}

function sameDay(one, other) {
  return (
    one.getFullYear() === other.getFullYear()
    && one.getMonth() === other.getMonth()
    && one.getDate() === other.getDate()
  );
}

function pad(number) {
  return String(number).padStart(2, '0');
}
