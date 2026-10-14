// Места работы, переведённые в то, что видно и что набирают.
//
// Чистые функции: строка опыта приходит доводом, наружу уходят строки.
// Ни моста, ни разметки этот файл не знает.

import { recordsGoing } from './records.js';
import { counted } from './words.js';

/** Период работы для шапки карточки.
 *
 * Месяц и год без дня: места работы различают по месяцам, а день удлиняет
 * строку вдвое. Открытый конец назван словами — по нему и читают, работает
 * человек здесь сейчас или нет.
 */
export function period(startIso, endIso) {
  if (!startIso) return '';
  const short = (iso) => {
    const [year, month] = iso.split('-');
    return `${month}.${year}`;
  };
  return `${short(startIso)} — ${endIso ? short(endIso) : 'настоящее время'}`;
}

/** Какие обязательные поля места работы пусты.
 *
 * Три поля, ровно те же, что требует мост (`repository/profile_experience`):
 * название, должность и дата начала. Сверять их надо здесь, потому что перечень
 * уезжает целиком и отбивается тоже целиком — одна недозаполненная карточка
 * отменяла бы правки всех соседних, заполненных. По этому же списку карточка
 * метит пустые поля.
 *
 * Даты конца среди них нет: «по настоящее время» — обычный случай.
 */
export function experienceMissing(exp) {
  return ['company', 'role', 'start_date'].filter((name) => !(exp[name] || '').trim());
}

/** Готово ли место работы к записи: обязательные поля заполнены. */
export function experienceReady(exp) {
  return experienceMissing(exp).length === 0;
}

/** Что из перечня мест работы уедет на мост — и почему не уедет ничего. */
export function experienceGoing(rows) {
  return recordsGoing(
    rows,
    experienceReady,
    (shown, whole) =>
      `Место работы #${shown}: заполните компанию, должность и дату начала — `
      + `пока они пусты, ${whole ? 'перечень мест работы' : 'оно'} не сохраняется.`,
  );
}

/** Чем подписана свёрнутая карточка.
 *
 * Карточки свёрнуты, и это всё, по чему человек их различает; безымянная
 * названа прямо, иначе её не отличить от пустого места в списке.
 */
export function cardTitle(exp) {
  return {
    name: exp.company || 'Без названия',
    role: exp.role || '',
    period: period(exp.start_date, exp.end_date),
  };
}

/** Места работы как вид записи вкладки профиля. */
export const EXPERIENCE = {
  key: 'experience',
  heading: 'Профиль / Experience',
  count: (n) => `${counted(n, 'место', 'места', 'мест')} работы`,
  addLabel: '+ Добавить место работы',
  blank: () => ({
    id: null,
    company: '',
    company_url: '',
    role: '',
    start_date: null,
    end_date: null,
    achievements: [],
    responsibilities: [],
    skill_names: [],
  }),
  going: experienceGoing,
  missing: experienceMissing,
  leaving: (one) => `Удалить место работы «${one.company || 'без названия'}»?`,
};
