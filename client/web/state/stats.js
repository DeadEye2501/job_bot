// Числа статистики, переведённые в то, что человек читает.
//
// Чистые функции: ответы моста приходят доводами, наружу уходят строки и доли.
// Ни моста, ни разметки этот файл не знает.

import { isoDay } from './dates.js';
import { blankFilter } from './vacancy_filter.js';

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
  { key: 'total', label: 'Всего вакансий', total: 'total', delta: 'total_period', tone: '' },
  { key: 'applied', label: 'Откликов отправлено', total: 'applied_total', delta: 'applied_period', tone: 'applied' },
  { key: 'in_progress', label: 'В процессе', total: 'in_progress_total', delta: 'in_progress_period', tone: 'progress' },
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

// Первый день выходных. Их два, и они последние: по ним низкий столбец читают
// не как тишину, а как нерабочий день.
const WEEKEND_FROM = 5;

/** Статусы, из которых вакансия ещё может сдвинуться, — левая колонка. */
const MOVING = ['New', 'Applied', 'Answered', 'Test', 'Invitation', 'In Progress'];

/** Исходы: отсюда вакансия уже не двигается, — правая колонка. */
const OVER = ['Offer', 'Decline', 'Ghosting', 'Scam', 'Not Fit'];

// На сколько колонок разложены навыки в карточке.
const SKILL_COLUMNS = 3;

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
export function weekBars(counts, applied = 0) {
  const top = Math.max(...counts, 0);
  return counts.map((count, at) => ({
    label: WEEKDAYS[at],
    count,
    weekend: at >= WEEKEND_FROM,
    // Ноль над столбцом читается как «писали, но не ответили». Пока не отправлен
    // ни один отклик, правду говорит прочерк.
    note: applied ? count : '—',
    percent: top ? (count / top) * 100 : 0,
  }));
}

/** Счётчики статусов двумя колонками: слева живые, справа отыгравшие.
 *
 * Показаны все одиннадцать, включая нулевые: ноль у «Офферов» — это новость.
 * Пропусти мы строку, человек прочёл бы список как «оффер ещё не заводили», а
 * не «ни одного не случилось».
 */
export function statusColumns(counts) {
  const named = (names) => names.map((name) => ({ name, count: counts[name] || 0 }));
  return [named(MOVING), named(OVER)];
}

/** Строки карточки навыков: доля от самого частого и место в колонке.
 *
 * Полосы читают друг относительно друга — доля от суммы сделала бы разницу
 * между вторым и третьим навыком неразличимой. Колонки заполняются сверху
 * вниз, и у первой строки каждой из них верхней черты нет: там она читалась
 * бы как граница карточки.
 */
export function skillRows(skills) {
  const top = Math.max(1, ...skills.map((one) => one.count));
  const inColumn = Math.ceil(skills.length / SKILL_COLUMNS);
  return skills.map((one, at) => ({
    ...one,
    percent: (one.count / top) * 100,
    first: inColumn > 0 && at % inColumn === 0,
  }));
}

/** Сколько строк встаёт в одну колонку карточки навыков. */
export function skillRowsPerColumn(skills) {
  return Math.ceil(skills.length / SKILL_COLUMNS);
}

/** Конверсия канала: подпись и доля для полоски-метра.
 *
 * Несчитанная названа словом, а не нулём: «0 %» значит «отклики были, ответов
 * нет», а не отправляли вовсе — другая новость, и путать их нельзя. Доля
 * округлена до целых: дробь в узкой колонке разъезжается, а решают по ней на
 * глаз.
 */
export function convNote(value) {
  if (value === null || value === undefined) return { text: 'n/a', percent: 0 };
  return { text: `${value.toFixed(0)}%`, percent: value };
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

// Сколько суток назад начинается квартал. Готового срока у отбора вакансий
// нет, и он уезжает туда парой дат.
const QUARTER_DAYS = 90;

// Как срок статистики называется у отбора вакансий. Совпавшие имена названы
// поимённо, а не пропущены: молчаливое совпадение переживёт переименование на
// одной из сторон, а этот список — нет.
const PRESET_BY_PERIOD = {
  today: 'today',
  week: 'week',
  month: 'month',
};

/** Отбор, с которым уходят в вакансии, нажав на строку статуса.
 *
 * Прежний отбор перетирается целиком, а не дополняется: человек просит
 * «покажи вакансии этого статуса», и уцелевший грейд позавчерашнего поиска
 * отдал бы ему пустой список вместо тех девяти штук, которые он только что
 * видел числом.
 *
 * Срок уезжает вместе со статусом: число под столбиком посчитано за него, и
 * без него на «New 9 за сегодня» открылись бы все New за всё время — человек
 * прочёл бы это как враньё счётчика. У квартала готового имени в отборе нет,
 * и он уезжает парой дат; у «всего времени» срока нет вовсе.
 *
 * Шкалы у числа и у списка при этом разные, и список шире. Число считает вход
 * в статус, а отбор списка режет по последней активности — а её поднимает и
 * письмо, и событие конвейера. Вакансия, вошедшая в статус внутри срока, в
 * список попадёт всегда (переход поднимает и активность), но рядом с ней
 * встанут и те, у кого в этот срок была любая другая жизнь. Свести шкалы
 * значило бы завести в отборе второе поле даты — этого не просили.
 *
 * `now` приходит доводом, как и у соседнего отбора вакансий: к часам этот
 * слой не ходит, иначе проверить квартал было бы нечем.
 */
export function sliceTarget(status, period, now) {
  const target = { ...blankFilter(), statuses: new Set([status]) };
  const preset = PRESET_BY_PERIOD[period];
  if (preset) return { ...target, datePreset: preset };
  if (period !== 'quarter') return target;
  // Отступ днями, а не миллисекундами: в сутки перевода часов их в дне не
  // 24 часа, и вычитание ровных суток съехало бы на час.
  const from = new Date(now);
  from.setDate(from.getDate() - QUARTER_DAYS);
  return {
    ...target,
    datePreset: 'range',
    dateFrom: isoDay(from.getFullYear(), from.getMonth() + 1, from.getDate()),
  };
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
