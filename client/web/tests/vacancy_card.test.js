// Следствия ленты карточки: что в ней видно, в каком порядке и что правится.

import { describe, expect, it } from 'vitest';

import { remoteLabel } from '../state/vacancies.js';
import { timelineRows } from '../state/vacancy_card.js';

// Причина пропуска видна человеку только строкой ленты, и проверяется она
// оттуда же: отдельного выхода наружу у перевода нет.
function parsedNote(skipReason) {
  const events = [
    {
      id: 1,
      kind: 'parsed',
      payload: { status: 'New', skip_reason: skipReason },
      created_at: '2026-08-14T11:00:00Z',
    },
  ];
  return timelineRows([], events)[0].text;
}

const HISTORY = [
  {
    id: 7,
    status: 'Applied',
    explanation: 'откликнулись.',
    applied: true,
    source: 'system',
    changed_at: '2026-08-14T12:00:00Z',
  },
  {
    id: 3,
    status: 'New',
    explanation: null,
    applied: true,
    source: 'user',
    changed_at: '2026-08-14T10:00:00Z',
  },
];

const EVENTS = [
  {
    id: 5,
    kind: 'parsed',
    payload: { status: 'New', skip_reason: 'score 3 < 5' },
    created_at: '2026-08-14T11:00:00Z',
  },
  {
    id: 1,
    kind: 'ingested',
    payload: { channel: 'jobs', msg_id: 42 },
    created_at: '2026-08-14T09:00:00Z',
  },
];

describe('лента карточки', () => {
  it('сливает историю с событиями и кладёт свежее сверху', () => {
    // Это одна жизнь вакансии, а не два списка: разбор, отклик и правки
    // человека читаются подряд, иначе причину нынешнего статуса не найти.
    const rows = timelineRows(HISTORY, EVENTS);
    expect(rows.map((one) => one.key)).toEqual(['h7', 'e5', 'h3', 'e1']);
  });

  it('удавшаяся авто-отправка и отправленный отклик в ленту не попадают', () => {
    // О них уже сказано статусом «Applied» строкой выше; повтор растил бы
    // ленту вдвое, ничего не добавляя.
    const events = [
      { id: 9, kind: 'auto_send', payload: { ok: true }, created_at: '2026-08-14T12:30:00Z' },
      { id: 8, kind: 'applied_sent', payload: { hr_id: 1 }, created_at: '2026-08-14T12:20:00Z' },
      ...EVENTS,
    ];
    const kinds = timelineRows(HISTORY, events).map((one) => one.kind);
    // Остальное на месте: отсев, съевший ленту целиком, прошёл бы одной
    // проверкой «нет лишнего».
    expect(kinds).toEqual(['history', 'parsed', 'history', 'ingested']);
  });

  it('неудавшаяся авто-отправка остаётся и названа причиной', () => {
    // Это единственное место, где человек узнаёт, почему отклик не ушёл сам.
    const events = [
      {
        id: 9,
        kind: 'auto_send',
        payload: { ok: false, reason: 'cv_missing' },
        created_at: '2026-08-14T12:30:00Z',
      },
    ];
    expect(timelineRows([], events)[0].text).toBe('Авто-отправка: CV-файл не найден.');
  });

  it('текущей помечена первая видимая строка, а не первая пришедшая', () => {
    // Свечение говорит «вот на чём вакансия стоит сейчас». Достанься оно
    // отброшенной строке, светилась бы пустота, а живая строка стояла бы
    // тусклой.
    const events = [
      { id: 9, kind: 'applied_sent', payload: {}, created_at: '2026-08-14T23:00:00Z' },
      ...EVENTS,
    ];
    const rows = timelineRows(HISTORY, events);
    expect(rows[0].key).toBe('h7');
    expect(rows.filter((one) => one.current).map((one) => one.key)).toEqual(['h7']);
  });

  it('комментарий без смены статуса точки не красит', () => {
    // Цветная точка значит «статус стал таким»; у записи, где статус не
    // менялся, она соврала бы о переходе, которого не было.
    const history = [{ ...HISTORY[0], applied: false }];
    expect(timelineRows(history, [])[0].status).toBe('');
  });

  it('правится только то, что поставил человек', () => {
    // Пояснения бота — след его работы, а не заметка: правка стирала бы то,
    // по чему потом разбираются, почему он так решил.
    const rows = timelineRows(HISTORY, []);
    expect(rows.map((one) => one.editable)).toEqual([false, true]);
    expect(rows[1].historyId).toBe(3);
  });

  it('чужая запись без пояснения названа словами, своя остаётся пустой', () => {
    // Чужую строку читают, свою правят: в первой пустое место читалось бы как
    // недогрузившееся, во второй оно и есть поле, в которое пишут.
    const history = [
      { ...HISTORY[0], explanation: null },
      { ...HISTORY[1], explanation: null },
    ];
    const rows = timelineRows(history, []);
    expect(rows[0].text).toBe('');
    expect(rows[1].text).toBe('');
  });

  it('при равном времени запись истории стоит выше события', () => {
    // База ставит им одну метку: разбор и записанный им же статус приходят
    // одной секундой, и статус — то, ради чего строку читают.
    const rows = timelineRows([{ ...HISTORY[0], changed_at: '2026-08-14T11:00:00Z' }], [EVENTS[0]]);
    expect(rows.map((one) => one.key)).toEqual(['h7', 'e5']);
  });

  it('разбор без замечаний назван словами', () => {
    // Пустое место читалось бы как недогрузившаяся строка.
    const events = [
      { id: 5, kind: 'parsed', payload: { status: 'New' }, created_at: '2026-08-14T11:00:00Z' },
    ];
    expect(timelineRows([], events)[0].text).toBe('Без замечаний.');
  });

  it('заведение руками названо словами', () => {
    // Незнакомый род лента печатает как есть, латиницей. Пропади перевод
    // этого рода — в ленте встало бы «created_by_hand» вместо фразы.
    const events = [
      { id: 6, kind: 'created_by_hand', payload: null, created_at: '2026-08-25T11:00:00Z' },
    ];
    expect(timelineRows([], events)[0].text).toBe('Вакансия добавлена вручную.');
  });

  it('поступление называет канал', () => {
    expect(timelineRows([], [EVENTS[1]])[0].text).toBe('Поступила из канала @jobs.');
  });

  it('строка разбора несёт всё, чем её рисуют', () => {
    // Точка красится статусом разбора, подпись говорит, что это про статус, а
    // время идёт отдельным полем: пропади любое — строка нарисуется калекой, а
    // лента останется зелёной.
    const row = timelineRows([], [EVENTS[0]])[0];
    expect(row.status).toBe('New');
    expect(row.label).toBe('New:');
    expect(row.when).toBe('2026-08-14T11:00:00Z');
  });

  it('событие без содержимого ленту не роняет', () => {
    // Мост сводит пустое содержимое к `null`, и такое приезжает от родов,
    // которым нечего рассказать: обращение к полю уронило бы всю ленту.
    const events = [{ id: 6, kind: 'parsed', payload: null, created_at: '2026-08-14T11:00:00Z' }];
    expect(timelineRows([], events)[0].text).toBe('Без замечаний.');
  });

  it('первая привязка компании называет пустую сторону прочерком', () => {
    // Привязали впервые — прежнего имени нет вовсе, и «Компания:  → Ромашка»
    // читалось бы как недогрузившаяся строка.
    const events = [
      {
        id: 4,
        kind: 'linked_company',
        payload: { previous_name: null, new_name: 'Ромашка' },
        created_at: '2026-08-14T13:00:00Z',
      },
    ];
    expect(timelineRows([], events)[0].text).toBe('Компания: не привязана → Ромашка.');
  });

  it('привязка HR называет обе стороны', () => {
    // Имена запечены в событии нарочно: HR могли переименовать или снести, а
    // запись должна остаться читаемой.
    const events = [
      {
        id: 4,
        kind: 'linked_hr',
        payload: { previous_name: 'Иван', new_name: 'Пётр' },
        created_at: '2026-08-14T13:00:00Z',
      },
    ];
    expect(timelineRows([], events)[0].text).toBe('HR: Иван → Пётр.');
  });

  it('строка истории подписана именем статуса, а не словом «Статус»', () => {
    // Каким стал статус — это и есть содержание строки. Одинаковая подпись у
    // всех оставляет эту сведению только в цвете точки, а цветов одиннадцать
    // и на глаз они не различаются.
    const rows = timelineRows(HISTORY, []);
    expect(rows.map((one) => one.label)).toEqual(['Applied:', 'New:']);
  });

  it('поступление без канала называет его неизвестным', () => {
    // Канал в событии может не сохраниться, и подстановка пустоты дала бы
    // «Поступила из канала @.» — строку, которую читают как поломку.
    const events = [{ id: 1, kind: 'ingested', payload: {}, created_at: '2026-08-14T09:00:00Z' }];
    expect(timelineRows([], events)[0].text).toBe('Поступила из канала неизвестного канала.');
  });

  it('привязка без имени называет сторону номером, а не прочерком', () => {
    // Имя запекается в событие, но у давних записей его нет: номер даёт
    // человеку хоть что-то, по чему привязку можно найти.
    const events = [
      {
        id: 4,
        kind: 'linked_hr',
        payload: { previous_id: 12, new_name: 'Пётр' },
        created_at: '2026-08-14T13:00:00Z',
      },
    ];
    expect(timelineRows([], events)[0].text).toBe('HR: #12 → Пётр.');
  });

  it('незнакомый род события не молчит', () => {
    // Роды заводит бэкенд, и новый приедет раньше, чем окно про него узнает:
    // пустая строка в ленте выглядела бы поломкой.
    const events = [{ id: 2, kind: 'спам', payload: {}, created_at: '2026-08-14T13:00:00Z' }];
    expect(timelineRows([], events)[0].text).toContain('спам');
  });
});

describe('формат работы в чипе', () => {
  it('назван по-русски, а не кодом моста', () => {
    // Код едет с моста и на мост; человеку он ничего не говорит, а чип с
    // надписью `remote` читается как недоделанная страница.
    expect(remoteLabel('remote')).toBe('Удалёнка');
    expect(remoteLabel('office')).toBe('Офис');
  });

  it('незнакомый формат едет как есть, а не теряется', () => {
    // Форматы заводит бэкенд, и новый приедет раньше, чем окно про него
    // узнает: пустой чип человек читает как поломку.
    expect(remoteLabel('remote_first')).toBe('remote_first');
  });
});

describe('причина пропуска словами', () => {
  it('оценка ниже порога названа обоими числами', () => {
    // По ним человек решает, двигать ли порог в настройках.
    expect(parsedNote('score 3 < 5')).toBe('Оценка 3 ниже порога 5.');
  });

  it('мусор и отсев названы по-русски', () => {
    expect(parsedNote('trash: реклама курсов')).toBe('Мусор: реклама курсов.');
    expect(parsedNote('blacklist: @spam')).toBe('Отсев: @spam.');
  });

  it('пустая вакансия названа одной фразой, без технического хвоста', () => {
    expect(parsedNote('empty: no title, no description')).toBe('Пустая вакансия.');
  });

  it('ответ модели остаётся как есть, без приставки', () => {
    // Модель отвечает готовой фразой; приставка «llm» человеку ничего не
    // говорит, а объяснение стоит после неё.
    expect(parsedNote('llm: не вакансия, а анонс митапа')).toBe('не вакансия, а анонс митапа.');
  });

  it('точка не удваивается', () => {
    expect(parsedNote('trash: реклама.')).toBe('Мусор: реклама.');
    expect(parsedNote('llm: это вопрос?')).toBe('это вопрос?');
  });

  it('незнакомая причина едет как есть, а не теряется', () => {
    // Коды заводит бэкенд, и новый приедет раньше, чем окно про него узнает:
    // проглоченная причина оставила бы человека без объяснения вовсе.
    expect(parsedNote('too_many_links')).toBe('too_many_links.');
  });
});
