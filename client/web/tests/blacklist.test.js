// Следствия чёрного списка: отбор, счёт по родам и слова подсказчика.

import { describe, expect, it } from 'vitest';

import {
  BLACKLIST_KINDS,
  blacklistCounts,
  blacklistHints,
  blacklistShown,
  valueField,
} from '../state/blacklist.js';

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

describe('поле значения в чёрном списке', () => {
  it('род «канал» подсказывает уже известные', () => {
    // Канал заводят из известных: набранный руками даст запись, которая ни с
    // чем не сойдётся, и отсев по ней не сработает.
    expect(valueField('channel').hints).toBe(true);
  });

  it('род «слово» подсказок не даёт', () => {
    // Слово — свободный набор, подсказывать нечего.
    expect(valueField('keyword').hints).toBe(false);
  });

  it('подсказка поля говорит, что набирать при этом роде', () => {
    // Одна подсказка на все роды заставляла бы гадать, ждут тут ник, имя или
    // кусок текста объявления.
    expect(valueField('hr').placeholder).toBe('@username HR или имя');
    expect(valueField('keyword').placeholder).toBe('Что блокировать (фрагмент текста вакансии)');
  });
});

describe('счёт строк отсева по родам', () => {
  const ROWS = [
    { kind: 'hr', value: '@a' },
    { kind: 'hr', value: '@b' },
    { kind: 'keyword', value: 'казино' },
  ];

  it('у каждой пилюли своё число', () => {
    // По ним видно, где строки вообще есть: пустой род нажимают и получают
    // пустой список, не понимая, отбор это или их нет вовсе.
    expect(blacklistCounts(ROWS).hr).toBe(2);
    expect(blacklistCounts(ROWS).company).toBe(0);
  });

  it('общая пилюля считает все строки', () => {
    expect(blacklistCounts(ROWS).all).toBe(3);
  });
});

describe('подсказчик существующих записей', () => {
  const ITEMS = [
    { value: '@irina_hr', label: 'Ирина', sub: '@irina_hr' },
    { value: '@petr', label: 'Пётр', sub: '@petr' },
  ];

  it('уже заведённые в подсказки не идут', () => {
    // Мост такую строку всё равно отобьёт как повтор, а человек до отказа
    // считал бы, что заносит новую.
    const shown = blacklistHints({
      items: ITEMS,
      rows: [{ kind: 'hr', value: '@IRINA_HR' }],
      kind: 'hr',
      typed: '',
    });
    expect(shown.options.map((one) => one.value)).toEqual(['@petr']);
  });

  it('набранное отбирает подсказки и по имени, и по значению', () => {
    expect(blacklistHints({ items: ITEMS, rows: [], kind: 'hr', typed: 'ирин' }).options)
      .toHaveLength(1);
    expect(blacklistHints({ items: ITEMS, rows: [], kind: 'hr', typed: '@petr' }).options)
      .toHaveLength(1);
  });

  it('пустота названа своей причиной', () => {
    // Три пустоты значат разное: заводить нечего, всё уже заведено, или не
    // нашлось по набранному — и чинятся они по-разному.
    expect(blacklistHints({ items: [], rows: [], kind: 'hr', typed: '' }).empty)
      .toBe('Нет существующих HR');
    expect(blacklistHints({
      items: ITEMS,
      rows: ITEMS.map((one) => ({ kind: 'hr', value: one.value })),
      kind: 'hr',
      typed: '',
    }).empty).toBe('Все уже в blacklist');
    expect(blacklistHints({ items: ITEMS, rows: [], kind: 'hr', typed: 'зз' }).empty)
      .toBe('Ничего не найдено');
  });

  it('пустой перечень назван предметом, а не его кодом', () => {
    // «Нет существующих channel» — след внутреннего имени рода: человек такого
    // слова на экране не заводил и читает его как поломку.
    expect(blacklistHints({ items: [], rows: [], kind: 'channel', typed: '' }).empty)
      .toBe('Нет существующих каналов');
  });

  it('когда есть что показать, пустого слова нет', () => {
    expect(blacklistHints({ items: ITEMS, rows: [], kind: 'hr', typed: '' }).empty).toBe('');
  });

  it('пока перечень не приехал, так и сказано', () => {
    // Иначе на месте ещё не пришедших подсказок стояло бы «нет существующих», и
    // человек набирал бы руками то, что вот-вот подсказали бы.
    expect(blacklistHints({ items: null, rows: [], kind: 'hr', typed: '' }).empty)
      .toBe('Загрузка…');
  });
});
