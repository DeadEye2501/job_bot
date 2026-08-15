// Отбор списка вакансий: из чего его собирают и что из него уезжает на мост.
//
// Чистые функции: отбор приходит доводом, наружу уходит то, что мост примет.
// «Сейчас» тоже довод — сроки считаются от него, и без довода их нельзя было бы
// проверить, не подменяя часы всей странице.

import { dayOf } from './dates.js';
import { GRADES } from './profile.js';

// Вариант «не отбираем». Пустая строка, а не слово: слово уехало бы на мост и
// искалось бы подстрокой внутри значения — грейд и формат он сверяет так.
const ANY = '';

const ALL = { value: ANY, label: 'Все' };

/** Грейды объявлены анкетой: значения те же — и туда, и сюда они ездят через
 *  мост, а второе их написание разошлось бы с первым молча. */
export const GRADE_CHOICES = [ALL, ...GRADES];

/** Форматы работы, какими их выбирают в отборе.
 *
 * Значения общие с анкетой — их читает мост, — а подписи и порядок свои:
 * здесь ищут прежде всего удалёнку, и стоит она первой.
 */
export const REMOTE_CHOICES = [
  ALL,
  { value: 'remote', label: 'Удалёнка' },
  { value: 'hybrid', label: 'Гибрид' },
  { value: 'office', label: 'Офис' },
];

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

// Статус в том виде, в каком его ждёт отбор: строчными и через дефис. Смена
// статуса, наоборот, принимает написанное значение — перепутай их, и отбор
// отсеется молча, а смена ответит «неверный статус».
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

// Выбранный день, доведённый до края суток. Невыбранной границы нет вовсе:
// период с одним краем — такой же период, как и с обоими.
function pickedDay(iso, edge) {
  if (!iso) return null;
  const { year, month, day } = dayOf(iso);
  return dayEdge(new Date(year, month - 1, day), edge);
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
    return { from: pickedDay(filter.dateFrom, DAY_START), to: pickedDay(filter.dateTo, DAY_END) };
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

const filled = (text) => text.trim() !== '';

// Девять групп панели: каждая стоит или не стоит. Вилка о двух половинах —
// одно условие, срок со своими датами — тоже одно: иначе «2 активных» на одной
// вилке человек читает как два разных отбора.
const CONDITIONS = [
  (filter) => filter.statuses.size > 0,
  (filter) => filter.channels.size > 0,
  (filter) => filter.companies.size > 0,
  (filter) => filled(filter.scoreMin) || filled(filter.scoreMax),
  (filter) => filled(filter.salaryMin) || filled(filter.salaryMax),
  (filter) => filter.grade !== ANY,
  (filter) => filter.remote !== ANY,
  (filter) => filter.hrContact !== ANY,
  (filter) => filter.datePreset !== ANY || filled(filter.dateFrom) || filled(filter.dateTo),
];

/** Сколько условий отбора сейчас стоит.
 *
 * Считается по выбранному в панели, а не по тому, что доехало до моста:
 * нажатый чип «Периода…» и набранный обрывок числа обязаны отозваться в
 * счётчике сразу, иначе нажатие выглядит непринятым.
 */
export function activeCount(filter) {
  return CONDITIONS.filter((stands) => stands(filter)).length;
}

/** Потолок перечня компаний. Их бывают тысячи, а панель под них — 140
 *  пикселей: без потолка открытие перерисовывало бы всю базу ради первых
 *  пяти строк. У каналов потолка нет — их десятки. */
export const COMPANY_MAX = 80;

/** Имена для выбора: просеянные поиском, выстроенные по-русски и обрезанные
 *  потолком, если его назвали.
 *
 * Мост отдаёт их в порядке базы — по кодам букв «ё» и строчные уехали бы в
 * хвост, и человек искал бы компанию не там, где её ждёт.
 */
export function pickNames(names, search, limit = names.length) {
  const needle = search.trim().toLowerCase();
  const found = needle ? names.filter((one) => one.toLowerCase().includes(needle)) : names;
  return [...found].sort((one, other) => one.localeCompare(other, 'ru')).slice(0, limit);
}
