// Отбор списка вакансий: из чего его собирают и что из него уезжает на мост.
//
// Чистые функции: отбор приходит доводом, наружу уходит то, что мост примет.
// «Сейчас» тоже довод — сроки считаются от него, и без довода их нельзя было бы
// проверить, не подменяя часы всей странице.

import { asIso } from './experience.js';
import { GRADES, WORK_FORMATS } from './profile.js';
import { STATUS_ORDER } from './stats.js';

// Вариант «не отбираем». Пустая строка, а не слово: слово уехало бы на мост и
// искалось бы подстрокой внутри значения — грейд и формат он сверяет так.
const ANY = '';

const ALL = { value: ANY, label: 'Все' };

/** Статусы в том порядке, в каком их читают в кольце статистики.
 *
 * Второго перечня статусов во фронте не заводится: разойдись он с первым —
 * чипы отбора называли бы не то, чем подписаны доли кольца. Значение чипа
 * совпадает с тем, каким статус приходит в строке списка, и им же покрашена
 * точка рядом.
 */
export const STATUS_CHOICES = STATUS_ORDER.map((one) => ({ value: one, label: one }));

/** Грейды и форматы работы объявлены анкетой: значения те же — и туда, и сюда
 *  они ездят через мост, а второе их написание разошлось бы с первым молча. */
export const GRADE_CHOICES = [ALL, ...GRADES];

export const REMOTE_CHOICES = [ALL, ...WORK_FORMATS];

export const HR_CHOICES = [
  ALL,
  { value: 'with', label: 'Только с HR' },
  { value: 'without', label: 'Только без HR' },
];

/** Сроки активности. Первый — тот, в котором список открывается. */
export const DATE_PRESETS = [
  ALL,
  { value: 'today', label: 'Дня' },
  { value: 'week', label: 'Недели' },
  { value: 'month', label: 'Месяца' },
  { value: 'range', label: 'Периода…' },
];

const DAY = 24 * 60 * 60 * 1000;

// Края суток в часах человека: мост сравнивает границу с меткой активности, а
// она записана мгновением, а не датой.
const DAY_START = [0, 0, 0, 0];
const DAY_END = [23, 59, 59, 999];

/** Отбор, каким его видят до первого нажатия. */
export function blankFilter() {
  return {
    statuses: new Set(),
    channels: new Set(),
    companies: new Set(),
    scoreMin: '',
    scoreMax: '',
    salaryMin: '',
    salaryMax: '',
    grade: ANY,
    remote: ANY,
    hrContact: ANY,
    datePreset: ANY,
    dateFrom: '',
    dateTo: '',
  };
}

// Статус в том виде, в каком его ждёт отбор на мосту: строчными и через дефис.
// В строке списка и на чипе он стоит написанным, а сверяется там по словарю
// кодов — незнакомый выбрасывается без единого слова окну.
function statusCode(status) {
  return status.toLowerCase().replace(/\s+/g, '-');
}

// Набранное число или ничего. Пустое и негодное — одно и то же: человек стирает
// поле и печатает заново, и на полпути там не граница, а обрывок.
function typedNumber(text) {
  const typed = text.trim();
  if (!typed) return null;
  const value = Number(typed);
  return Number.isFinite(value) ? value : null;
}

function dayEdge(date, [hours, minutes, seconds, ms]) {
  const edge = new Date(date);
  edge.setHours(hours, minutes, seconds, ms);
  return edge.toISOString();
}

// Набранный день, доведённый до края суток. Границей уезжает только целая и
// существующая дата: недобранное человек набирает посимвольно, а «31.02» часы
// перекатывают на март — и отбор молча пошёл бы не по тем суткам.
function typedDay(text, edge) {
  const iso = asIso(text);
  if (iso === null) return null;
  const [year, month, day] = iso.split('-').map(Number);
  const at = new Date(year, month - 1, day);
  if (at.getMonth() + 1 !== month || at.getDate() !== day) return null;
  return dayEdge(at, edge);
}

// Границы срока. У недели и месяца верхней нет: она отрезала бы то, что
// приехало минуту назад.
function dates(filter, now) {
  if (filter.datePreset === 'today') {
    return { from: dayEdge(now, DAY_START), to: dayEdge(now, DAY_END) };
  }
  if (filter.datePreset === 'week') {
    return { from: new Date(now.getTime() - 7 * DAY).toISOString(), to: null };
  }
  if (filter.datePreset === 'month') {
    return { from: new Date(now.getTime() - 30 * DAY).toISOString(), to: null };
  }
  if (filter.datePreset === 'range') {
    return { from: typedDay(filter.dateFrom, DAY_START), to: typedDay(filter.dateTo, DAY_END) };
  }
  return { from: null, to: null };
}

function putNumber(payload, key, text) {
  const value = typedNumber(text);
  if (value !== null) payload[key] = value;
}

/** Отбор в том виде, в каком его принимает `vacancies.list`.
 *
 * Невыбранное не уезжает ключом вовсе: пустое значение мост читает как
 * условие, которого не было, а пустой список — как «не отбирали», и лишний
 * ключ сузил бы выдачу сам собой.
 */
export function filterPayload(filter, now) {
  const payload = {};
  if (filter.statuses.size) payload.statuses = [...filter.statuses].map(statusCode);
  if (filter.channels.size) payload.channels = [...filter.channels];
  if (filter.companies.size) payload.companies = [...filter.companies];
  putNumber(payload, 'score_min', filter.scoreMin);
  putNumber(payload, 'score_max', filter.scoreMax);
  putNumber(payload, 'salary_min', filter.salaryMin);
  putNumber(payload, 'salary_max', filter.salaryMax);
  if (filter.grade) payload.grade = filter.grade;
  if (filter.remote) payload.remote = filter.remote;
  if (filter.hrContact) payload.hr_contact = filter.hrContact;
  const { from, to } = dates(filter, now);
  if (from) payload.date_from = from;
  if (to) payload.date_to = to;
  return payload;
}

// Ключи, из которых собирается одно условие. Вилка о двух половинах — одно
// условие, срок с обеими границами — тоже одно: иначе «2 активных» на одной
// вилке человек читает как два разных отбора.
const CONDITIONS = [
  ['statuses'],
  ['channels'],
  ['companies'],
  ['score_min', 'score_max'],
  ['salary_min', 'salary_max'],
  ['grade'],
  ['remote'],
  ['hr_contact'],
  ['date_from', 'date_to'],
];

/** Сколько условий отбора сейчас стоит.
 *
 * Считается по тому же, что уезжает на мост, а не по заполненности полей:
 * выбранный срок без набранных дат ничего не сужает, и насчитанное над ним
 * условие зажигало бы воронку над полным списком — то есть врало бы ровно о
 * том, ради чего она заведена.
 */
export function activeCount(filter, now) {
  const sent = filterPayload(filter, now);
  return CONDITIONS.filter((keys) => keys.some((key) => key in sent)).length;
}

/** Имена для выбора: просеянные поиском и выстроенные по-русски.
 *
 * Мост отдаёт их в порядке базы — по кодам букв «ё» и строчные уехали бы в
 * хвост, и человек искал бы компанию не там, где её ждёт.
 */
export function pickNames(names, search) {
  const needle = search.trim().toLowerCase();
  const found = needle ? names.filter((one) => one.toLowerCase().includes(needle)) : names;
  return [...found].sort((one, other) => one.localeCompare(other, 'ru'));
}
