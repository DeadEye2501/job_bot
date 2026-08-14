// Числа статистики, переведённые в то, что человек читает.
//
// Чистые функции: ответы моста приходят доводами, наружу уходят строки и доли.
// Ни моста, ни разметки этот файл не знает.

/** Сроки, за которые считают, — от короткого к длинному.
 *
 * `delta` — как называется прирост за этот срок. У «всего времени» его нет:
 * сравнивать не с чем, это и есть всё время.
 */
export const PERIODS = [
  { key: 'today', label: 'Сегодня', delta: 'за сегодня' },
  { key: 'week', label: 'Неделя', delta: 'за неделю' },
  { key: 'month', label: 'Месяц', delta: 'за месяц' },
  { key: 'quarter', label: 'Квартал', delta: 'за квартал' },
  { key: 'all', label: 'Всё время', delta: '' },
];

/** Показатели верхнего ряда.
 *
 * Имена полей названы поимённо, а не собраны по общему правилу: у счёта
 * вакансий имя без приставки, у остальных с ней. Припиши мы приставку всем —
 * счётчик показывал бы ноль при живой дельте рядом.
 *
 * `tone` — цвет числа, тот же, что был в прежнем окне.
 */
export const KPI = [
  { key: 'total', label: 'Всего', total: 'total', delta: 'total_period', tone: '' },
  { key: 'applied', label: 'Откликов', total: 'applied_total', delta: 'applied_period', tone: 'applied' },
  { key: 'in_progress', label: 'В работе', total: 'in_progress_total', delta: 'in_progress_period', tone: 'progress' },
  { key: 'offer', label: 'Офферов', total: 'offer_total', delta: 'offer_period', tone: 'offer' },
  { key: 'decline', label: 'Отказов', total: 'decline_total', delta: 'decline_period', tone: 'decline' },
];

/** Порядок статусов в кольце — по воронке, а не по тому, как их прислал мост.
 *
 * Кольцо читают по часовой стрелке: «новая → отклик → ответ → …». Придёт
 * ответ в другом порядке — и воронка перестанет быть воронкой. */
export const STATUS_ORDER = [
  'New', 'Applied', 'Answered', 'Test', 'Invitation', 'In Progress',
  'Offer', 'Decline', 'Ghosting', 'Scam', 'Not Fit',
];

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

/** Верхний ряд показателей: число, подпись и прирост — по каждому.
 *
 * Имена полей названы поимённо в `KPI`, а собираются здесь: у счёта вакансий
 * имя без приставки, у остальных с ней, и припиши мы приставку всем — счётчик
 * показывал бы ноль при живой дельте рядом. Пропущенное число — ноль, а не
 * пустота: мост не присылает поля, которого не считал, а пустое место в ряду
 * читается как поломка.
 */
export function kpiRow(answer, period) {
  return KPI.map((one) => ({
    key: one.key,
    label: one.label,
    tone: one.tone,
    total: answer[one.total] ?? 0,
    delta: deltaNote(answer[one.delta], period),
  }));
}

/** Столбцы ответов по дням недели.
 *
 * Высота считается от самого высокого дня, а не от суммы: столбцы читают друг
 * относительно друга, и доля от суммы сделала бы разницу между понедельником
 * и пятницей неразличимой.
 */
export function weekBars(counts) {
  const top = Math.max(...counts, 0);
  return counts.map((count, at) => ({
    label: WEEKDAYS[at],
    count,
    percent: top ? (count / top) * 100 : 0,
  }));
}

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** Срок человеческой мерой.
 *
 * Мера подбирается по величине: ответы приходят и через минуту, и через
 * неделю, и «10080 минут» там, где человек ждёт «7 д», не читается. Крупная
 * мера договаривает остаток — «2 ч» вместо «2 ч 30 мин» занижает ожидание
 * вдвое.
 *
 * Неизвестное отмечено прочерком: ноль читался бы как «отвечают мгновенно» —
 * прямая ложь про выборку, где не ответил никто.
 */
export function duration(seconds) {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < MINUTE) return `${Math.round(seconds)} с`;
  if (seconds < HOUR) return `${Math.round(seconds / MINUTE)} мин`;
  if (seconds < DAY) return withRest(seconds, HOUR, 'ч', MINUTE, 'мин');
  return withRest(seconds, DAY, 'д', HOUR, 'ч');
}

function withRest(seconds, big, bigName, small, smallName) {
  const whole = Math.floor(seconds / big);
  const rest = Math.round((seconds - whole * big) / small);
  return rest > 0 ? `${whole} ${bigName} ${rest} ${smallName}` : `${whole} ${bigName}`;
}

/** Прирост за срок: знак, число и то, за какой именно срок.
 *
 * Без подписи число не читается — «+3» за квартал и за сегодня разные новости.
 * Ноль показан знаком равенства, а не пустотой: пустое место читалось бы как
 * «не посчитали».
 */
export function deltaNote(value, period) {
  const about = PERIODS.find((one) => one.key === period);
  if (value === null || value === undefined || !about?.delta) return null;
  const sign = value > 0 ? '+' : value < 0 ? '−' : '±';
  return { text: `${sign}${Math.abs(value)} ${about.delta}`, tone: value > 0 ? 'up' : '' };
}

/** Доли кольца статусов.
 *
 * Пустые статусы не попадают вовсе: кольцо копило бы невидимые сегменты, и
 * подписи под ним разошлись бы с тем, что видно. Пустая выборка кольца не
 * рисует — нулевой круг вырождается в точку.
 */
export function donut(counts) {
  const total = Object.values(counts).reduce((sum, one) => sum + (one || 0), 0);
  if (!total) return [];
  return STATUS_ORDER.filter((name) => counts[name] > 0).map((name) => ({
    name,
    count: counts[name],
    percent: (counts[name] / total) * 100,
  }));
}
