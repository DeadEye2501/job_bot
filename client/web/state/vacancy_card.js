// Жизнь вакансии одной лентой: записи истории статусов и события разбора,
// переведённые в строки, которые читают.
//
// Чистые функции: списки приходят доводами, наружу уходят строки. Ни моста, ни
// разметки этот файл не знает.

import { atHandle } from './telegram.js';

// Роды событий, которых в ленте не бывает: об удавшейся отправке уже сказано
// статусом «Applied» строкой выше, и повтор растил бы ленту вдвое, ничего не
// добавляя.
const HIDDEN = new Set(['applied_sent']);

// Отказы авто-отправки словами. Коды приходят с бэкенда
// (`backend/flows/apply.py`), и это единственное место, где человек узнаёт,
// почему отклик не ушёл сам.
const SEND_FAILS = {
  profile_empty: 'профиль пуст',
  cover_letter_failed: 'письмо не прошло проверку',
  cover_letter_unasked: 'модель не ответила',
  cv_missing: 'CV-файл не найден',
  race: 'статус успел измениться',
  blocked: 'отправка заблокирована',
  telegram_error: 'Telegram отказался',
  flood_wait: 'Telegram держит FloodWait',
};

// Приставки причин пропуска: чем начинается ответ бэкенда и каким словом это
// называется в ленте.
const SKIP_PREFIXES = [
  { starts: 'llm: ', word: '' },
  { starts: 'trash: ', word: 'Мусор: ' },
  { starts: 'blacklist: ', word: 'Отсев: ' },
];

const SCORE_SKIP = /^score\s+(-?\d+)\s*<\s*(-?\d+)$/i;

const ENDINGS = /[.!?…:]$/;

// Точка в конце, если её нет. Строки ленты стоят вперемешку — фраза модели,
// наша подпись, пояснение человека, — и без общего окончания соседние
// выглядели бы по-разному.
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

// Сторона привязки: имя, номер или слова о пустоте. Имена запекаются в
// событие, но у давних записей их нет — по номеру привязку хотя бы найдут.
function linkSide(name, id, blank) {
  if (name) return name;
  return id === null || id === undefined ? blank : `#${id}`;
}

function linkNote(what, payload, blank) {
  const was = linkSide(payload.previous_name, payload.previous_id, blank);
  const now = linkSide(payload.new_name, payload.new_id, blank);
  return `${what}: ${was} → ${now}.`;
}

// Способы отклика вне Telegram словами — в той форме, в какой они встают после
// «Отклик …». Коды приходят с бэкенда (`ApplicationVia`).
const VIA = { aggregator: 'на сайте агрегатора', form: 'формой работодателя', email: 'письмом' };

/** Способ отклика словами; незнакомый код называется сам собой — коды заводит
 *  бэкенд, и новый приедет раньше, чем окно про него узнает. */
function viaWords(method) {
  return VIA[method] || method;
}

// Кто писал письмо отклика: по этой строке сравнивают два способа на живых
// откликах (настройка `letter_writer`).
const WRITER = { app: 'приложение', agent: 'агент' };

function appliedNote(payload) {
  const simulated = payload.simulated ? ' (симуляция)' : '';
  return `Отклик ${viaWords(payload.via)}${simulated}; письмо: ${WRITER[payload.letter_by] || 'без письма'}.`;
}

// Подписи событий по роду. Таблицей, а не цепочкой сравнений: каждый новый род
// удлинял бы одну функцию.
const EVENT_TEXT = {
  ingested: (payload) =>
    `Поступила из канала ${atHandle(payload.channel) || 'неизвестного канала'}.`,
  created_by_hand: () => 'Вакансия добавлена вручную.',
  parsed: (payload) => skipNote(payload.skip_reason) || 'Без замечаний.',
  auto_send: (payload) => `Авто-отправка: ${SEND_FAILS[payload.reason] || payload.reason}.`,
  linked_hr: (payload) => linkNote('HR', payload, 'не привязан'),
  linked_company: (payload) => linkNote('Компания', payload, 'не привязана'),
  // «Поиск по сети» — способ поиска, а не место: «Найдена на Поиск по сети»
  // читалось бы как ошибка.
  found: (payload) => (payload.web_search ? 'Найдена в сети.' : `Найдена на ${payload.source}.`),
  applied_elsewhere: appliedNote,
  apply_failed: (payload) =>
    `Отклик не удался (${viaWords(payload.method)}): ${payload.reason}.`,
  vacancy_closed: () => 'Вакансия закрыта на сайте.',
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

// Удавшаяся авто-отправка молчит по тому же доводу, что и `applied_sent`;
// неудавшаяся остаётся — ради неё род и показывают.
function worthShowing(one) {
  if (HIDDEN.has(one.kind)) return false;
  return !(one.kind === 'auto_send' && (one.payload || {}).ok === true);
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
 * читаются подряд, иначе причину нынешнего статуса не найти.
 *
 * Отметка «текущая» достаётся первой видимой строке, а не первой пришедшей:
 * достанься она отброшенной, светилась бы пустота.
 */
export function timelineRows(history, events) {
  const rows = [...history.map(historyRow), ...events.filter(worthShowing).map(eventRow)];
  rows.sort(newerFirst);
  return rows.map((one, at) => ({ ...one, current: at === 0 }));
}
