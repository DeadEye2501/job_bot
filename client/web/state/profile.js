// Анкета и резюме, переведённые в то, что видно на экране.
//
// Чистые функции: ответ моста приходит доводом, наружу уходят строки и числа.
// Ни моста, ни разметки этот файл не знает.

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

/** Уровни языка от высшего к младшему: родной и высокий выбирают чаще всего,
 *  и они должны попадаться первыми. */
export const LANG_LEVELS = ['native', 'C2', 'C1', 'B2', 'B1', 'A2', 'A1'];

const KB = 1024;
const MB = KB * KB;

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

/** Что показать про файл резюме: имя, подпись под ним и признак пропажи.
 *
 * Пропажа названа отдельно и словами: путь в настройках есть, бот прикладывает
 * резюме к каждому отклику, а файла на диске нет — молчи об этом экран, человек
 * узнал бы об этом от HR.
 */
export function cvNote(meta) {
  if (!meta) return { name: 'Файл не выбран', note: '', missing: false };
  const missing = !meta.exists;
  const parts = [fileSize(meta.size)];
  if (missing) parts.push('файл не найден');
  return { name: meta.name, note: parts.join(' · '), missing };
}

/** Когда анкету правили в последний раз.
 *
 * Отметка нужна потому, что кнопки «сохранить» на экране нет: по ней человек и
 * понимает, что запись дошла.
 */
export function updatedNote(iso) {
  if (!iso) return '—';
  const at = new Date(iso);
  const two = (number) => String(number).padStart(2, '0');
  const date = `${at.getFullYear()}-${two(at.getMonth() + 1)}-${two(at.getDate())}`;
  return `обновлено ${date} ${two(at.getHours())}:${two(at.getMinutes())}`;
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
    title: '',
    email: '',
    phone: '',
    telegram_username: '',
    github_url: '',
    location: '',
    education: '',
    free_preferences: '',
    grades: [],
    work_format: [],
    languages: [],
    updated_at: null,
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
