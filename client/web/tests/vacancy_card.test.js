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

  it('текущей помечена самая свежая строка', () => {
    // Свечение говорит «вот на чём вакансия стоит сейчас».
    const rows = timelineRows(HISTORY, EVENTS);
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

  it('заведённое руками по ссылке называет и источник', () => {
    // Пост по ссылке человек заводит сам, а пришёл он из канала: лента говорит
    // и то и другое, иначе источник вакансии в ней пропал бы.
    const events = [{
      id: 7, kind: 'created_by_hand',
      payload: { via: 'ingested', channel: 'jobs', msg_id: 5 }, created_at: '2026-08-25T11:00:00Z',
    }];
    expect(timelineRows([], events)[0].text).toBe('Вакансия добавлена вручную. Поступила из канала @jobs.');
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

  it('строка истории подписана именем статуса, а не словом «Статус»', () => {
    // Каким стал статус — это и есть содержание строки. Одинаковая подпись у
    // всех оставляет эту сведению только в цвете точки, а цветов одиннадцать
    // и на глаз они не различаются.
    const rows = timelineRows(HISTORY, []);
    expect(rows.map((one) => one.label)).toEqual(['Applied:', 'New:']);
  });

  it('поступление без ника канала так и названо', () => {
    // Ника нет у закрытого канала, а подстановка пустоты дала бы «Поступила из
    // канала @.» — строку, которую читают как поломку.
    const events = [{ id: 1, kind: 'ingested', payload: {}, created_at: '2026-08-14T09:00:00Z' }];
    expect(timelineRows([], events)[0].text).toBe('Поступила из канала без ника.');
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

// Строка ленты одного события — так, как её видит человек.
function eventNote(kind, payload) {
  return timelineRows([], [{ id: 1, kind, payload, created_at: '2026-10-10T11:00:00Z' }])[0].text;
}

describe('события агрегаторов в ленте', () => {
  it('найденная агентом названа своим источником', () => {
    expect(eventNote('found', { source: 'Пример', url: 'https://example.test/v/1', web_search: false }))
      .toBe('Найдена на Пример.');
  });

  it('найденная поиском по сети названа своей подписью', () => {
    // «Поиск по сети» — способ поиска, а не место: «Найдена на Поиск по сети»
    // читалось бы как ошибка.
    expect(eventNote('found', { source: 'Поиск по сети', url: 'https://example.test/v/1', web_search: true }))
      .toBe('Найдена в сети.');
  });
});
