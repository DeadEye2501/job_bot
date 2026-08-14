// Жизнь вакансии одной лентой: записи истории статусов и события разбора,
// переведённые в строки, которые читают.
//
// Чистые функции: списки приходят доводами, наружу уходят строки. Ни моста, ни
// разметки этот файл не знает.

// Роды событий, которых в ленте не бывает: об удавшейся отправке уже сказано
// статусом «Applied» строкой выше, и повтор растил бы ленту вдвое, ничего не
// добавляя.
const HIDDEN = new Set(['applied_sent']);

// Отказы авто-отправки словами. Коды приходят с бэкенда
// (`backend/flows/apply.py`), и это единственное место, где человек узнаёт,
// почему отклик не ушёл сам.
const SEND_FAILS = {
  no_vacancy: 'вакансия уже удалена',
  profile_empty: 'профиль пуст',
  cover_letter_failed: 'письмо не прошло проверку',
  cv_missing: 'файл резюме не найден',
  race: 'статус успел измениться',
  blocked: 'отправка заблокирована',
  telegram_error: 'Telegram отказался принять сообщение',
  flood_wait: 'Telegram попросил подождать',
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
  if (text === 'unparseable') return 'Не удалось разобрать.';
  const lower = text.toLowerCase();
  if (lower.startsWith('empty: ')) return 'Пустая вакансия.';
  const known = SKIP_PREFIXES.find((one) => lower.startsWith(one.starts));
  if (known === undefined) return ended(text);
  return ended(known.word + text.slice(known.starts.length));
}

function linkNote(what, payload) {
  return `${what}: ${payload.previous_name || '—'} → ${payload.new_name || '—'}.`;
}

// Чем подписано событие. Незнакомый род называется сам собой: роды заводит
// бэкенд, и новый приедет раньше, чем окно про него узнает, — пустая строка в
// ленте выглядела бы поломкой.
function eventText(kind, payload) {
  if (kind === 'ingested') return `Поступила из канала @${payload.channel}.`;
  if (kind === 'parsed') return skipNote(payload.skip_reason) || 'Без замечаний.';
  if (kind === 'auto_send') {
    return `Авто-отправка: ${SEND_FAILS[payload.reason] || payload.reason}.`;
  }
  if (kind === 'linked_hr') return linkNote('HR', payload);
  if (kind === 'linked_company') return linkNote('Компания', payload);
  return `Событие: ${kind}.`;
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
    label: 'Статус:',
    text: editable ? one.explanation || '' : ended(one.explanation || 'Без комментария'),
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
    label: one.kind === 'parsed' ? 'Статус:' : '',
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
