// Жизнь вакансии одной лентой: записи истории статусов и события разбора,
// переведённые в строки, которые читают.
//
// Чистые функции: списки приходят доводами, наружу уходят строки. Ни моста, ни
// разметки этот файл не знает.

import { atHandle } from './telegram.js';

// Приставки причин пропуска: чем начинается ответ бэкенда и каким словом это
// называется в ленте.
const SKIP_PREFIXES = [
  { starts: 'llm: ', word: '' },
  { starts: 'trash: ', word: 'Мусор: ' },
  { starts: 'blacklist: ', word: 'Отсев: ' },
];

const SCORE_SKIP = /^score\s+(-?\d+)\s*<\s*(-?\d+)$/i;

const ENDINGS = /[.!?…:][»"')\]]*$/;

// Точка в конце, если её нет. Строки ленты стоят вперемешку — фраза модели,
// наша подпись, пояснение человека, — и без общего окончания соседние
// выглядели бы по-разному. Зеркало `backend/domain/sentence.py`: знак конца
// виден и за закрывающей кавычкой или скобкой.
function ended(text) {
  const trimmed = text.trimEnd();
  if (!trimmed || ENDINGS.test(trimmed)) return trimmed;
  return `${trimmed}.`;
}

// Причина, по которой вакансию пропустили, — словами. Бэкенд отвечает
// техническим кодом с приставкой; приставка человеку ничего не говорит, а
// объяснение стоит после неё.
function skipNote(raw) {
  if (!raw) return '';
  const text = String(raw);
  const score = SCORE_SKIP.exec(text);
  if (score !== null) return `Оценка ${score[1]} ниже порога ${score[2]}.`;
  const lower = text.toLowerCase();
  if (lower.startsWith('empty: ')) return 'Пустая вакансия.';
  const known = SKIP_PREFIXES.find((one) => lower.startsWith(one.starts));
  if (known === undefined) return ended(text);
  return ended(known.word + text.slice(known.starts.length));
}

// Подписи событий по роду. Таблицей, а не цепочкой сравнений: каждый новый род
// удлинял бы одну функцию.
const EVENT_TEXT = {
  ingested: (payload) =>
    `Поступила из канала ${atHandle(payload.channel) || 'неизвестного канала'}.`,
  created_by_hand: () => 'Вакансия добавлена вручную.',
  parsed: (payload) => skipNote(payload.skip_reason) || 'Без замечаний.',
  // «Поиск по сети» — способ поиска, а не место: «Найдена на Поиск по сети»
  // читалось бы как ошибка.
  found: (payload) => (payload.web_search ? 'Найдена в сети.' : `Найдена на ${payload.source}.`),
};

// Чем подписано событие. Незнакомый род называется сам собой: роды заводит
// бэкенд, и новый приедет раньше, чем окно про него узнает, — пустая строка в
// ленте выглядела бы поломкой.
function eventText(kind, payload) {
  const text = EVENT_TEXT[kind];
  return text ? text(payload) : kind;
}

function moment(iso) {
  const at = Date.parse(iso);
  return Number.isNaN(at) ? Number.NEGATIVE_INFINITY : at;
}

/** Своя запись правится, чужая читается: пояснение бота — след его работы, а не
 *  заметка, и правка стирала бы то, по чему потом разбираются. */
function historyRow(one) {
  const editable = one.source === 'user';
  return {
    key: `h${one.id}`,
    kind: 'history',
    // Цветная точка значит «статус стал таким»: у записи, где статус не
    // менялся, она соврала бы о переходе, которого не было.
    status: one.applied ? one.status : '',
    // Подпись — имя статуса: каким он стал, и есть содержание строки. Общее
    // слово оставило бы эту сведению только в цвете точки, а цветов
    // одиннадцать и на глаз они не различаются.
    label: `${one.status}:`,
    text: editable ? one.explanation || '' : ended(one.explanation || ''),
    when: one.changed_at,
    at: moment(one.changed_at),
    historyId: one.id,
    editable,
  };
}

function eventRow(one) {
  const payload = one.payload || {};
  return {
    key: `e${one.id}`,
    kind: one.kind,
    status: one.kind === 'parsed' ? payload.status || '' : '',
    label: one.kind === 'parsed' && payload.status ? `${payload.status}:` : '',
    text: eventText(one.kind, payload),
    when: one.created_at,
    at: moment(one.created_at),
    historyId: null,
    editable: false,
  };
}

// Свежее сверху. При равной метке запись истории стоит выше события: база
// ставит им одно время — разбор и записанный им же статус приходят одной
// секундой, — а статус и есть то, ради чего строку читают.
function newerFirst(one, other) {
  if (one.at !== other.at) return one.at < other.at ? 1 : -1;
  return (one.historyId === null ? 1 : 0) - (other.historyId === null ? 1 : 0);
}

/** Лента карточки: история и события в одном порядке.
 *
 * Это одна жизнь вакансии, а не два списка: разбор, отклик и правки человека
 * читаются подряд, иначе причину нынешнего статуса не найти. Отметка
 * «текущая» — у самой свежей строки.
 */
export function timelineRows(history, events) {
  const rows = [...history.map(historyRow), ...events.map(eventRow)];
  rows.sort(newerFirst);
  return rows.map((one, at) => ({ ...one, current: at === 0 }));
}
