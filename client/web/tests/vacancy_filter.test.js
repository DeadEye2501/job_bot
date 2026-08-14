// Следствия отбора вакансий: что уезжает на мост и сколько условий насчитано.

import { describe, expect, it } from 'vitest';

import {
  DATE_PRESETS,
  GRADE_CHOICES,
  HR_CHOICES,
  REMOTE_CHOICES,
  STATUS_CHOICES,
  activeCount,
  blankFilter,
  filterPayload,
  pickNames,
} from '../state/vacancy_filter.js';

const NOW = new Date(2026, 7, 14, 21, 0, 0);

describe('пустой отбор', () => {
  it('не шлёт на мост ни одного условия', () => {
    // Пустой отбор значит «показать всё»: уедь оттуда хоть одно поле, список
    // сузился бы сам собой, а человек не выбирал ничего.
    expect(filterPayload(blankFilter(), NOW)).toEqual({});
  });

  it('насчитывает ноль условий', () => {
    expect(activeCount(blankFilter(), NOW)).toBe(0);
  });
});

describe('статусы', () => {
  it('уезжают кодами, а не тем, что написано на чипе', () => {
    // Мост ждёт коды строчными и через дефис (`in-progress`), а на чипе стоит
    // значение, каким статус приходит в строке списка. Уедь написанное —
    // условие отсеялось бы молча, и человек читал бы список без отбора.
    const filter = { ...blankFilter(), statuses: new Set(['In Progress', 'Not Fit']) };
    expect(filterPayload(filter, NOW).statuses).toEqual(['in-progress', 'not-fit']);
  });

  it('выбор нескольких — одно условие, а не по одному на статус', () => {
    const filter = { ...blankFilter(), statuses: new Set(['New', 'Applied', 'Offer']) };
    expect(activeCount(filter, NOW)).toBe(1);
  });

  it('каждый статус перечня уезжает кодом, годным для моста', () => {
    // Мост сверяет коды по словарю и незнакомый выбрасывает, ничего не сказав
    // окну: остался бы в коде пробел или заглавная — чип нажимался бы, а отбор
    // по нему не работал.
    const filter = { ...blankFilter(), statuses: new Set(STATUS_CHOICES.map((one) => one.value)) };
    const codes = filterPayload(filter, NOW).statuses;
    expect(codes.every((code) => /^[a-z-]+$/.test(code))).toBe(true);
  });
});

describe('вариант «Все»', () => {
  it('у грейда, формата и HR-контакта не уезжает вовсе', () => {
    // Грейд и формат мост сверяет подстрокой: уедь туда слово варианта «Все»,
    // оно искалось бы внутри значения — и список опустел бы начисто.
    const filter = {
      ...blankFilter(),
      grade: GRADE_CHOICES[0].value,
      remote: REMOTE_CHOICES[0].value,
      hrContact: HR_CHOICES[0].value,
    };
    expect(filterPayload(filter, NOW)).toEqual({});
    expect(activeCount(filter, NOW)).toBe(0);
  });

  it('выбранный грейд, формат и HR-контакт уезжают своими значениями', () => {
    const filter = { ...blankFilter(), grade: 'senior', remote: 'remote', hrContact: 'with' };
    expect(filterPayload(filter, NOW)).toEqual({
      grade: 'senior',
      remote: 'remote',
      hr_contact: 'with',
    });
    expect(activeCount(filter, NOW)).toBe(3);
  });

  it('оба варианта контакта HR названы теми словами, которые мост различает', () => {
    // Слов ровно два, и сверяются они точным сравнением: назови вариант иначе —
    // чип нажимался бы, а список приходил бы неотобранным.
    const [, withHr, withoutHr] = HR_CHOICES;
    expect(filterPayload({ ...blankFilter(), hrContact: withHr.value }, NOW).hr_contact).toBe('with');
    expect(filterPayload({ ...blankFilter(), hrContact: withoutHr.value }, NOW).hr_contact).toBe(
      'without',
    );
  });
});

describe('числовые вилки', () => {
  it('набранные числа уезжают числами, а не строками', () => {
    // Мост читает их числовыми читалками: строка «60» дошла бы, а «60 » уже
    // нет, и граница пропала бы молча.
    const filter = {
      ...blankFilter(),
      scoreMin: '60',
      scoreMax: '90',
      salaryMin: '100000',
      salaryMax: '300000',
    };
    expect(filterPayload(filter, NOW)).toEqual({
      score_min: 60,
      score_max: 90,
      salary_min: 100000,
      salary_max: 300000,
    });
  });

  it('недобранное и негодное не уезжает', () => {
    // Человек стирает поле и печатает заново; на полпути там пусто или минус
    // без числа — граница из такого получилась бы нулевой.
    const filter = { ...blankFilter(), scoreMin: '  ', scoreMax: '-', salaryMin: 'abc' };
    expect(filterPayload(filter, NOW)).toEqual({});
  });

  it('обе половины вилки — одно условие', () => {
    // Счётчик считает условия отбора, а не заполненные поля: «2 активных» на
    // одной вилке человек читает как два разных отбора.
    const filter = { ...blankFilter(), scoreMin: '60', scoreMax: '90' };
    expect(activeCount(filter, NOW)).toBe(1);
  });
});

describe('срок активности', () => {
  it('«Дня» — это сутки от полуночи до полуночи', () => {
    // Границы считаются в часах человека, а не в UTC: за окном вечер, и
    // «сегодня» по Гринвичу отрезало бы половину его дня.
    const payload = filterPayload({ ...blankFilter(), datePreset: 'today' }, NOW);
    expect(payload.date_from).toBe(new Date(2026, 7, 14, 0, 0, 0, 0).toISOString());
    expect(payload.date_to).toBe(new Date(2026, 7, 14, 23, 59, 59, 999).toISOString());
  });

  it('«Недели» — скользящее окно назад, без верхней границы', () => {
    // Верхняя граница отрезала бы то, что приехало минуту назад.
    const payload = filterPayload({ ...blankFilter(), datePreset: 'week' }, NOW);
    expect(payload.date_from).toBe(new Date(2026, 7, 7, 21, 0, 0).toISOString());
    expect(payload.date_to).toBeUndefined();
  });

  it('«Месяца» отсчитывает тридцать дней и тоже без верхней границы', () => {
    const payload = filterPayload({ ...blankFilter(), datePreset: 'month' }, NOW);
    expect(payload.date_from).toBe(new Date(2026, 6, 15, 21, 0, 0).toISOString());
    expect(payload.date_to).toBeUndefined();
  });

  it('«Периода» берёт набранные даты целыми сутками', () => {
    // Набирают дату, а отбирают по метке со временем: конец дня взят
    // последней миллисекундой, иначе вакансии этого дня выпали бы.
    const payload = filterPayload(
      { ...blankFilter(), datePreset: 'range', dateFrom: '01.08.2026', dateTo: '14.08.2026' },
      NOW,
    );
    expect(payload.date_from).toBe(new Date(2026, 7, 1, 0, 0, 0, 0).toISOString());
    expect(payload.date_to).toBe(new Date(2026, 7, 14, 23, 59, 59, 999).toISOString());
  });

  it('недобранная дата периода не уезжает', () => {
    // Человек набирает посимвольно, и `01.08.20` на полпути — не дата.
    const payload = filterPayload(
      { ...blankFilter(), datePreset: 'range', dateFrom: '01.08.20', dateTo: '' },
      NOW,
    );
    expect(payload).toEqual({});
  });

  it('несуществующая дата не уезжает границей', () => {
    // Часы перекатывают «31.02.2026» на третье марта: набранное выглядело бы
    // принятым, а отбор шёл бы по другим суткам, и сказать об этом было бы
    // нечему.
    const payload = filterPayload(
      { ...blankFilter(), datePreset: 'range', dateFrom: '31.02.2026' },
      NOW,
    );
    expect(payload).toEqual({});
  });

  it('срок и его даты — одно условие', () => {
    const filter = { ...blankFilter(), datePreset: 'range', dateFrom: '01.08.2026' };
    expect(activeCount(filter, NOW)).toBe(1);
  });

  it('выбранный период без набранных дат условием не считается', () => {
    // Воронка светится, пока список показан не весь; над полным списком она
    // говорила бы неправду ровно о том, ради чего заведена.
    const filter = { ...blankFilter(), datePreset: 'range' };
    expect(activeCount(filter, NOW)).toBe(0);
  });

  it('«Все» дат не ставит', () => {
    const payload = filterPayload({ ...blankFilter(), datePreset: DATE_PRESETS[0].value }, NOW);
    expect(payload).toEqual({});
  });
});

describe('каналы и компании', () => {
  it('уезжают списками, а не наборами', () => {
    // Набор мост читает как пустой список: `str_list` берёт только массив, а
    // всё прочее сводит к пустоте — отбор пропал бы, не сказав ни слова.
    const filter = { ...blankFilter(), channels: new Set(['jobs']), companies: new Set(['Ромашка']) };
    expect(filterPayload(filter, NOW)).toEqual({ channels: ['jobs'], companies: ['Ромашка'] });
  });

  it('считаются двумя разными условиями', () => {
    const filter = { ...blankFilter(), channels: new Set(['jobs']), companies: new Set(['Ромашка']) };
    expect(activeCount(filter, NOW)).toBe(2);
  });
});

describe('перечень для выбора', () => {
  it('выстроен по-русски, а не по кодам букв', () => {
    // Мост отдаёт их в порядке базы; «ё» и строчные по кодам уехали бы в
    // хвост, и человек искал бы компанию не там, где ждёт.
    expect(pickNames(['Яблоко', 'ёлка', 'Ромашка'], '')).toEqual(['ёлка', 'Ромашка', 'Яблоко']);
  });

  it('просеивается поиском, не глядя на регистр и на пробелы по краям', () => {
    // Набранное приходит как есть: заглавная и случайный пробел в конце иначе
    // оставили бы список пустым, а человек видел бы своё слово в поле.
    expect(pickNames(['Ромашка', 'РомБ', 'Астра'], '  РОМ ')).toEqual(['Ромашка', 'РомБ']);
  });

  it('не переставляет пришедший с моста перечень', () => {
    // Перечень приезжает в ответе и остаётся лежать в состоянии экрана:
    // переставь его сортировка на месте, порядок съехал бы и там, где на него
    // никто не просил смотреть.
    const names = ['Яблоко', 'ёлка', 'Ромашка'];
    pickNames(names, '');
    expect(names).toEqual(['Яблоко', 'ёлка', 'Ромашка']);
  });
});
