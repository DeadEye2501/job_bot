// Следствия переписки: дни, время, отметки о доставке и запрет отправки.

import { describe, expect, it } from 'vitest';

import { attachmentKind, byDays, chatTime, sendBlock, tick, unread } from '../state/chat.js';

const NOW = new Date('2026-08-14T21:00:00');

describe('лента переписки по дням', () => {
  it('письма одного дня стоят под одной подписью', () => {
    // Иначе подпись дня встала бы над каждым письмом и лента превратилась бы в
    // чересполосицу дат.
    const days = byDays(
      [
        { id: 1, sent_at: '2026-08-14T09:00:00' },
        { id: 2, sent_at: '2026-08-14T10:00:00' },
        { id: 3, sent_at: '2026-08-13T10:00:00' },
      ],
      NOW,
    );
    expect(days.map((one) => one.messages.length)).toEqual([2, 1]);
  });

  it('сегодняшний и вчерашний дни названы словами', () => {
    // Дату сегодняшнего письма человек читает как «когда-то»: слово говорит
    // быстрее числа.
    const days = byDays(
      [{ id: 1, sent_at: '2026-08-14T09:00:00' }, { id: 2, sent_at: '2026-08-13T09:00:00' }],
      NOW,
    );
    expect(days.map((one) => one.day)).toEqual(['Сегодня', 'Вчера']);
  });

  it('день этого года — без года, прошлого — с ним', () => {
    const days = byDays(
      [{ id: 1, sent_at: '2026-05-03T09:00:00' }, { id: 2, sent_at: '2025-05-03T09:00:00' }],
      NOW,
    );
    expect(days.map((one) => one.day)).toEqual(['3 мая', '3 мая 2025']);
  });

  it('месяц назван сокращённо', () => {
    // Подпись дня стоит посреди ленты и делит её надвое: полное название
    // месяца растягивает эту черту на пол-ленты.
    const days = byDays(
      [{ id: 1, sent_at: '2026-04-12T09:00:00' }, { id: 2, sent_at: '2025-09-12T09:00:00' }],
      NOW,
    );
    expect(days.map((one) => one.day)).toEqual(['12 апр', '12 сен 2025']);
  });

  it('письмо без времени в ленту не попадает', () => {
    // Такое приходит от записей, потерявших дату при переносе: поставить его
    // некуда, а под чужой подписью дня оно соврало бы.
    expect(byDays([{ id: 1, sent_at: null }], NOW)).toEqual([]);
  });
});

describe('время письма', () => {
  it('часы и минуты с ведущим нулём', () => {
    // «9:5» читается как сломанное.
    expect(chatTime('2026-08-14T09:05:00')).toBe('09:05');
  });
});

describe('отметка о доставке', () => {
  it('прочитанное своё письмо помечено двумя галочками', () => {
    expect(tick({ is_incoming: false, is_deleted: false, read_at: '2026-08-14T10:00:00' })).toBe('✓✓');
  });

  it('непрочитанное своё — одной', () => {
    expect(tick({ is_incoming: false, is_deleted: false, read_at: null })).toBe('✓');
  });

  it('на чужих письмах отметки нет', () => {
    // Галочка говорит «дошло до собеседника»; на его собственном письме она
    // означала бы неизвестно что.
    expect(tick({ is_incoming: true, is_deleted: false, read_at: null })).toBe('');
  });

  it('на удалённом письме отметки нет', () => {
    expect(tick({ is_incoming: false, is_deleted: true, read_at: '2026-08-14T10:00:00' })).toBe('');
  });
});

describe('есть ли что отмечать прочитанным', () => {
  it('чужое непрочитанное письмо отмечать надо', () => {
    expect(unread([{ is_incoming: true, read_at: null, is_deleted: false }])).toBe(true);
  });

  it('свои письма прочитанными не отмечают', () => {
    // Отметка говорит «я прочитал»; на своём письме она означала бы неизвестно
    // что, а зов ушёл бы в Telegram впустую.
    expect(unread([{ is_incoming: false, read_at: null, is_deleted: false }])).toBe(false);
  });

  it('удалённое письмо отмечать нечего', () => {
    expect(unread([{ is_incoming: true, read_at: null, is_deleted: true }])).toBe(false);
  });

  it('в прочитанной ленте отмечать нечего', () => {
    // Иначе зов уходил бы на каждое открытие карточки и на каждую отправку.
    expect(unread([{ is_incoming: true, read_at: '2026-08-14T10:00:00', is_deleted: false }])).toBe(false);
  });
});

describe('можно ли отправлять', () => {
  it('человеку с ником отправлять можно', () => {
    expect(sendBlock({ telegram_username: 'irina_hr', telegram_user_id: null, blacklist_value: null }))
      .toBe('');
  });

  it('человеку из отсева — нельзя, и сказано почему', () => {
    // Отправка ушла бы в обход собственного заслона бота.
    expect(sendBlock({ telegram_username: 'irina_hr', telegram_user_id: 7, blacklist_value: '@irina_hr' }))
      .toBe('HR в blacklist (@irina_hr) — переписка отключена');
  });

  it('без ника и номера учётной записи — нельзя', () => {
    // Адресата взять неоткуда: отправка не нашла бы собеседника.
    expect(sendBlock({ telegram_username: '', telegram_user_id: null, blacklist_value: null }))
      .toBe('Невозможно отправить — нет Telegram-контакта');
  });

  it('ник из одних пробелов адресатом не считается', () => {
    // Такой ник ложится в колонку и выглядит заполненным, а отправка по нему
    // собеседника не находит.
    expect(sendBlock({ telegram_username: '   ', telegram_user_id: null, blacklist_value: null }))
      .toBe('Невозможно отправить — нет Telegram-контакта');
  });

  it('одного номера учётной записи довольно', () => {
    expect(sendBlock({ telegram_username: '', telegram_user_id: 4242, blacklist_value: null })).toBe('');
  });
});

describe('вложение в письме', () => {
  it('картинка показывается фотографией', () => {
    // В образце фото видно прямо в переписке; строкой со скрепкой оно требует
    // выйти из окна, чтобы понять, что прислали.
    expect(attachmentKind({ media_kind: 'photo', media_path: '/media/1.jpg' })).toBe('photo');
  });

  it('прочее остаётся вложением-файлом', () => {
    expect(attachmentKind({ media_kind: 'document', media_path: '/media/cv.pdf' })).toBe('file');
  });

  it('нескачанное вложение названо, но не открывается', () => {
    // Бот скачивает не всё: открывать нечего, а сказать, что вложение было,
    // надо — иначе письмо выглядит пустым.
    expect(attachmentKind({ media_kind: 'photo', media_path: null })).toBe('gone');
  });

  it('письмо без вложения вложения не показывает', () => {
    expect(attachmentKind({ media_kind: null, media_path: null })).toBe('');
  });
});
