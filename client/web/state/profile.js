// Анкета и резюме, переведённые в то, что видно на экране.
//
// Чистые функции: ответ моста приходит доводом, наружу уходят строки и числа.
// Ни моста, ни разметки этот файл не знает.

import { showStamp } from './dates.js';
import { KB, MB } from './units.js';

/** Грейды, какими их выбирают в анкете. Значения едут на мост и совпадают с
 *  перечнем `backend/domain/taxonomy.py`. */
export const GRADES = [
  { value: 'junior', label: 'Junior' },
  { value: 'middle', label: 'Middle' },
  { value: 'senior', label: 'Senior' },
  { value: 'lead', label: 'Lead' },
];

/** Форматы работы. Значения те же, что у грейдов, — с моста и на мост. */
export const WORK_FORMATS = [
  { value: 'office', label: 'Офис' },
  { value: 'remote', label: 'Удалённо' },
  { value: 'hybrid', label: 'Гибрид' },
];

/** Пол — для родовых форм в письмах и ответах, которые агент пишет за человека.
 *  Значения совпадают с перечнем `Gender` модели анкеты. */
export const GENDERS = [
  { value: 'male', label: 'М' },
  { value: 'female', label: 'Ж' },
];

/** Валюты ожидаемой зарплаты — знаками, какими их хранит мост. Перечень тот
 *  же, что у разбора валют (`backend/domain/currency.py`): другое мост не
 *  узнает и запишет пустоту. */
export const CURRENCIES = ['₽', '$', '€', '₸', '֏', '₾'];

/** За какой срок названа ожидаемая зарплата. Значения — перечень `SalaryPeriod`. */
export const SALARY_PERIODS = [
  { value: 'hour', label: 'В час' },
  { value: 'month', label: 'В месяц' },
  { value: 'year', label: 'В год' },
];

/** Уровни языка от высшего к младшему: родной и высокий выбирают чаще всего,
 *  и они должны попадаться первыми. */
export const LANG_LEVELS = ['native', 'C2', 'C1', 'B2', 'B1', 'A2', 'A1'];

/** Размер файла человеческими единицами.
 *
 * Доли килобайта не показываются: они ничего не говорят и занимают место в
 * строке. У мегабайтов дробь оставлена — 1.2 и 1.9 МБ это разные файлы.
 */
export function fileSize(bytes) {
  const size = Number(bytes) || 0;
  if (size < KB) return `${size} Б`;
  if (size < MB) return `${(size / KB).toFixed(0)} КБ`;
  return `${(size / MB).toFixed(1)} МБ`;
}

/** Что показать про файл резюме: имя и подпись под ним.
 *
 * Пропажа названа словами: путь в настройках есть, бот прикладывает резюме к
 * каждому отклику, а файла на диске нет — молчи об этом экран, человек узнал
 * бы об этом от HR.
 */
export function cvNote(meta) {
  if (!meta) return { name: 'Файл не выбран', note: '' };
  const parts = [fileSize(meta.size)];
  if (!meta.exists) parts.push('файл не найден');
  return { name: meta.name, note: parts.join(' · ') };
}

/** Можно ли открыть файл резюме: открывать нечего, когда файла нет на диске —
 *  система показала бы свою ошибку вместо нашей строки «файл не найден». */
export function cvOpenable(meta) {
  return Boolean(meta?.exists);
}

/** Когда анкету правили в последний раз.
 *
 * Отметка нужна потому, что кнопки «сохранить» на экране нет: по ней человек и
 * понимает, что запись дошла.
 */
export function updatedNote(iso) {
  const stamp = showStamp(iso);
  return stamp ? `обновлено ${stamp}` : '—';
}

/** Строки, у которых есть имя.
 *
 * Правило одно на навыки и места работы: свежая строка рождается пустой, и
 * человек в этот миг ещё набирает её название. Уедь она на мост, он отказал бы
 * всей записи разом — а запись идёт после каждой правки.
 */
export function named(rows, key) {
  return rows.filter((one) => (one[key] || '').trim());
}

/** Незаполненная анкета.
 *
 * Все поля разом, а не половина: мост принимает анкету целиком, и пропущенное
 * уехало бы `undefined`, стерев то, что в базе уже лежало.
 */
export function blankProfile() {
  return {
    first_name: '',
    last_name: '',
    first_name_latin: '',
    last_name_latin: '',
    gender: '',
    title: '',
    email: '',
    phone: '',
    telegram_username: '',
    github_url: '',
    location: '',
    education: '',
    free_preferences: '',
    expected_salary: '',
    expected_salary_currency: '',
    expected_salary_period: '',
    grades: [],
    work_format: [],
    languages: [],
    updated_at: null,
  };
}

/** Анкета целиком — тем видом, каким её принимает мост.
 *
 * Сумма уезжает одними цифрами: «150 000» человек пишет так, как привык
 * читать, а мост считает суммой только число, и с пробелом между разрядами
 * она легла бы пустотой. В поле при этом остаётся набранное как есть.
 */
export function profileSheet(form, grades, formats) {
  return {
    ...form,
    expected_salary: String(form.expected_salary ?? '').replace(/\s/g, ''),
    grades: [...grades],
    work_format: [...formats],
  };
}

/** Пустая строка языка.
 *
 * Уровень задан средним: пустой мост не примет, а «native» по умолчанию соврал
 * бы за человека в анкете, которую читает HR.
 */
export function langRow() {
  return { language: '', level: 'B2' };
}
