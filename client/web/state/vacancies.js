// Вакансия, переведённая в то, что видно строкой списка.
//
// Чистые функции: строки моста приходят доводами, наружу уходят строки.
// «Сейчас» тоже довод — без него давность нельзя было бы проверить, не подменяя
// часы всей странице.

import { GRADES as PROFILE_GRADES } from './profile.js';

/** Порядки списка в том виде, в каком их выбирают. Ключи уезжают на мост и
 *  совпадают с перечнем `backend/repository/vacancies_list.VACANCY_SORTS`;
 *  первый — тот, в котором список открывается. */
export const SORTS = [
  { key: 'newest', label: 'Сначала новые' },
  { key: 'oldest', label: 'Сначала старые' },
  { key: 'score_desc', label: 'Сначала высокие баллы' },
  { key: 'score_asc', label: 'Сначала низкие баллы' },
  { key: 'status_active_first', label: 'Сначала активные статусы' },
  { key: 'status_new_first', label: 'Сначала новые статусы' },
];

// Грейды объявлены анкетой: значения те же самые — и там, и здесь они приходят
// с моста, — а второе их написание разошлось бы с первым молча.
const GRADES = Object.fromEntries(PROFILE_GRADES.map((one) => [one.value, one.label]));

// Сколько пунктов стека помещается в строку. Строка держится в одну высоту, а
// остальное человек увидит в карточке.
const CHIPS = 3;

// Во сколько раз оценка должна превысить порог, чтобы читаться уверенной. Порог
// — это черта, по которой бот решает откликаться; сразу над ней стоят те, кого
// он взял с натяжкой.
const SURE = 1.5;

/** Чем подписана строка вакансии.
 *
 * Под названием — компания, грейд, зарплата и давность: по ним вакансию узнают
 * в списке, не открывая. Отдаются они порознь, а не склеенной строкой: красятся
 * половины по-разному — компанию читают первой, давность последней. Пустая
 * половина названа прочерком: пустое место читалось бы как недогрузившаяся
 * строка.
 *
 * Давность берётся по последнему движению: по нему же идёт порядок в списке, и
 * разойдись они, свежая сверху строка называла бы себя месячной.
 */
export function vacancyLine(vacancy, now) {
  return {
    title: vacancy.title || '—',
    company: vacancy.company || '—',
    grade: vacancy.grade ? GRADES[vacancy.grade] || vacancy.grade : '—',
    salary: vacancy.salary || '—',
    when: ago(vacancy.last_activity_at || vacancy.posted_at || vacancy.created_at, now),
  };
}

/** Давность словом: от «только что» до месяцев.
 *
 * Точность падает вместе с давностью нарочно: «3 мин» человеку важно, «87 дней»
 * — нет, и месяц он читает быстрее.
 */
export function ago(iso, now) {
  if (!iso) return '—';
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return '—';
  const minutes = Math.floor(Math.max(0, now.getTime() - at) / 60000);
  if (minutes < 1) return 'только что';
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} д`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks} нед`;
  return `${Math.floor(days / 30)} мес`;
}

/** Каким цветом читается оценка рядом с порогом отбора.
 *
 * Порог — черта, по которой бот решает откликаться, и оценка говорит не сама о
 * себе, а о своём отношении к ней. Без оценки или без порога цвета нет вовсе:
 * неразобранную вакансию красить было бы враньём, а до первого ответа моста
 * сравнивать не с чем.
 */
export function scoreTone(score, threshold) {
  if (score === null || score === undefined || typeof threshold !== 'number') return '';
  if (score < threshold) return 'bad';
  return score < threshold * SURE ? 'warn' : 'good';
}

/** Ключ порядка по его подписи.
 *
 * Выпадающий список работает словами, а мост — ключами: уедь туда подпись,
 * отбор молча вернулся бы к умолчанию, и человек читал бы список не в том
 * порядке, который выбрал. Незнакомая подпись сводится к первому порядку по
 * тому же доводу.
 */
export function sortKey(label) {
  return (SORTS.find((one) => one.label === label) || SORTS[0]).key;
}

/** Что из стека помещается в строку и сколько осталось за ней.
 *
 * Правило живёт здесь, а не в разметке: число одно, а мест, где его пришлось бы
 * написать, два — сами чипы и подпись «сколько ещё».
 */
export function shownStack(stack) {
  return { chips: stack.slice(0, CHIPS), more: Math.max(0, stack.length - CHIPS) };
}
