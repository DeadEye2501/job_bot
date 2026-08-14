// Следствия списков контактов: отбор, отметки и слова.

import { describe, expect, it } from 'vitest';

import { BLACKLIST_KINDS, blacklistShown, channelName, fresher } from '../state/contacts.js';

describe('имя канала в списке', () => {
  it('название показывают, а ник — под ним', () => {
    // По названию канал узнают, по нику ищут: показать одно вместо другого
    // значит заставить искать вручную.
    expect(channelName({ title: 'Python Jobs', username: 'py_jobs' }))
      .toEqual({ name: 'Python Jobs', handle: '@py_jobs' });
  });

  it('без названия имя берут из ника', () => {
    // Название приходит не всегда — канал мог не отдать его при подписке.
    // Пустая строка выглядела бы как сломанная запись.
    expect(channelName({ title: '', username: 'py_jobs' }))
      .toEqual({ name: '@py_jobs', handle: '' });
  });

  it('без ника и названия канал назван номером', () => {
    // Такое бывает у приватных каналов: показать нечего, но строка должна
    // остаться нажимаемой.
    expect(channelName({ id: 42, title: '', username: '' }))
      .toEqual({ name: 'Канал #42', handle: '' });
  });
});

describe('отбор чёрного списка', () => {
  const rows = [
    { id: 1, kind: 'hr', value: 'spammer', reason: '' },
    { id: 2, kind: 'company', value: 'ООО Ромашка', reason: 'обман' },
    { id: 3, kind: 'keyword', value: 'крипта', reason: '' },
  ];

  it('род отбирают пилюлями', () => {
    // Роды правят по одному: перемешанные, они не читаются — у каждого свой
    // смысл значения.
    expect(blacklistShown(rows, { kind: 'hr', search: '' }).map((one) => one.id)).toEqual([1]);
  });

  it('без выбранного рода показывают всё', () => {
    expect(blacklistShown(rows, { kind: '', search: '' })).toHaveLength(3);
  });

  it('поиск идёт и по значению, и по причине', () => {
    // Причину пишут словами вроде «обман» — по ней и вспоминают, за что
    // строка заведена.
    expect(blacklistShown(rows, { kind: '', search: 'ромашк' }).map((one) => one.id)).toEqual([2]);
    expect(blacklistShown(rows, { kind: '', search: 'обман' }).map((one) => one.id)).toEqual([2]);
  });

  it('поиск не различает регистр', () => {
    // Человек набирает как придётся, а значения приходят как записаны.
    expect(blacklistShown(rows, { kind: '', search: 'КРИПТА' }).map((one) => one.id)).toEqual([3]);
  });

  it('роды перечислены с общим первым', () => {
    // «Все» стоит первым: это положение, в котором экран открывается.
    expect(BLACKLIST_KINDS[0].key).toBe('');
  });
});

describe('ответы, устаревшие в пути', () => {
  it('свежим считается ответ на последний вопрос', () => {
    // Человек набирает поиск посимвольно, и ответы возвращаются вразнобой:
    // ляг первый поверх третьего — в списке оказались бы чужие строки.
    expect(fresher(3, 3)).toBe(true);
    expect(fresher(2, 3)).toBe(false);
  });
});
