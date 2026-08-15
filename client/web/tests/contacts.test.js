// Следствия списков контактов: отбор, отметки и слова.

import { describe, expect, it } from 'vitest';

import {
  BLACKLIST_KINDS,
  blacklistShown,
  channelName,
  fresher,
  initials,
  linkReady,
  named,
  personCandidate,
  personLine,
  personName,
  unreadLine,
} from '../state/contacts.js';

describe('строка непрочитанной переписки', () => {
  it('человека с именем и ником называют именем, а ник ставят под ним', () => {
    // Список открывают, чтобы ответить, — и отвечают человеку, а не нику.
    expect(unreadLine({ hr_id: 7, name: 'Анна', telegram_username: 'anna' }))
      .toEqual({ name: 'Анна', sub: '@anna' });
  });

  it('без имени человека называют ником, и второй строки не заводят', () => {
    // Ник, повторённый под самим собой, занимает место и ничего не добавляет.
    expect(unreadLine({ hr_id: 7, name: '', telegram_username: 'anna' }))
      .toEqual({ name: '@anna', sub: '' });
  });

  it('без имени и без ника остаётся номер', () => {
    // Строка должна остаться нажимаемой: за ней переписка, которую ждут.
    expect(unreadLine({ hr_id: 7, name: null, telegram_username: null }))
      .toEqual({ name: 'HR #7', sub: '' });
  });
});

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

describe('имя человека в чужой карточке', () => {
  it('человека называют его именем', () => {
    expect(personName({ id: 3, name: 'Ирина', telegram_username: 'irina_hr' })).toBe('Ирина');
  });

  it('без имени человека называют ником', () => {
    // Имя приходит из переписки и бывает пустым — ник же есть почти всегда, и
    // по нему человека узнают в самом Telegram.
    expect(personName({ id: 3, name: '', telegram_username: 'irina_hr' })).toBe('@irina_hr');
  });

  it('без имени и ника человек назван номером', () => {
    // Такое приходит от учётных записей, скрывших ник: строка должна остаться
    // читаемой, а не пустой.
    expect(personName({ id: 12, name: '', telegram_username: '' })).toBe('Человек #12');
  });
});

describe('подпись человека в списке', () => {
  it('под именем стоят ник и компания', () => {
    // Однофамильцев и тёзок в переписке хватает: различают их по нику, а
    // вспоминают — по компании, из которой человек писал последний раз.
    expect(personLine({ id: 1, name: 'Ирина', telegram_username: 'irina_hr', last_company_name: 'Ромашка' }))
      .toEqual({ name: 'Ирина', sub: '@irina_hr · Ромашка' });
  });

  it('без ника так и сказано', () => {
    // Пустое место читалось бы как недогрузившаяся строка, а отсутствие ника
    // тут говорящее: такому человеку не отправить ничего.
    expect(personLine({ id: 1, name: 'Ирина', telegram_username: '', last_company_name: 'Ромашка' }))
      .toEqual({ name: 'Ирина', sub: 'без ника · Ромашка' });
  });

  it('без компании так и сказано', () => {
    expect(personLine({ id: 1, name: 'Ирина', telegram_username: 'irina_hr', last_company_name: null }))
      .toEqual({ name: 'Ирина', sub: '@irina_hr · без компании' });
  });

  it('имя берут тем же правилом, что и в чужой карточке', () => {
    // Разойдись эти два правила — один и тот же человек назывался бы в списке
    // и в карточке компании по-разному.
    expect(personLine({ id: 9, name: '', telegram_username: 'irina_hr', last_company_name: null }).name)
      .toBe('@irina_hr');
  });
});

describe('чем человек назван при заведении', () => {
  it('имени довольно', () => {
    expect(named({ name: 'Ирина', telegram_username: '', telegram_user_id: '' })).toBe(true);
  });

  it('ника довольно', () => {
    expect(named({ name: '', telegram_username: 'irina_hr', telegram_user_id: '' })).toBe(true);
  });

  it('номера учётной записи довольно', () => {
    // Так приходят те, кто скрыл ник: отправка находит собеседника по номеру,
    // и карточка с одним лишь им — рабочая.
    expect(named({ name: '', telegram_username: '', telegram_user_id: '4242' })).toBe(true);
  });

  it('одни пробелы именем не считаются', () => {
    // Иначе завелась бы карточка, которую не найти ни поиском, ни отправкой, —
    // а удалять её пришлось бы руками.
    expect(named({ name: '  ', telegram_username: ' ', telegram_user_id: '' })).toBe(false);
  });

  it('заметки именем не делают', () => {
    // Заметки не ссылаются на человека ничем: по ним его не найти.
    expect(named({ name: '', telegram_username: '', telegram_user_id: '', notes: 'звонил в мае' })).toBe(false);
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

describe('запор кнопки «Связать»', () => {
  it('пока никого не выбрали, связывать нечем', () => {
    expect(linkReady({ current: 4, chosen: null })).toBe(false);
  });

  it('выбор того же, кто уже привязан, кнопку не отпирает', () => {
    // Иначе нажатие переписывает привязку тем же значением и пишет в журнал
    // перемену, которой не было.
    expect(linkReady({ current: 4, chosen: 4 })).toBe(false);
  });

  it('выбор другого отпирает кнопку', () => {
    expect(linkReady({ current: 4, chosen: 9 })).toBe(true);
  });

  it('выбор при пустой привязке отпирает кнопку', () => {
    expect(linkReady({ current: null, chosen: 9 })).toBe(true);
  });
});

describe('буквы вместо снимка', () => {
  it('имя и фамилия дают две буквы', () => {
    // Снимок есть не у всех: у заведённых руками его нет вовсе, а пустой
    // кружок в списке читается как недогрузившаяся картинка.
    expect(initials('Иван Петров')).toBe('ИП');
  });

  it('одно слово даёт одну букву', () => {
    expect(initials('иван')).toBe('И');
  });

  it('из трёх слов берут первое и последнее', () => {
    expect(initials('Иван Иванович Петров')).toBe('ИП');
  });

  it('безымянному букв не достаётся', () => {
    // Тогда на его месте встаёт значок, а не пустой кружок.
    expect(initials('')).toBe('');
    expect(initials(null)).toBe('');
  });
});

describe('строка кандидата в окне выбора', () => {
  const PERSON = {
    id: 4,
    name: 'Ирина',
    telegram_username: 'irina_hr',
    last_company_name: 'Ромашка',
    vacancy_count: 3,
    avatar: 'data:image/png;base64,x',
    is_blacklisted: false,
  };

  it('называет человека тем же, чем и список контактов', () => {
    // Один и тот же человек, названный в списке и в подборщике по-разному,
    // читается как двое разных.
    expect(personCandidate(PERSON)).toEqual({
      id: 4,
      icon: 'person',
      avatar: 'data:image/png;base64,x',
      name: 'Ирина',
      sub: '@irina_hr · Ромашка',
      count: 3,
      blocked: false,
    });
  });

  it('отсеянный помечен отдельно', () => {
    // Приглушённая строка говорит, что связывать с ним бот всё равно не будет.
    expect(personCandidate({ ...PERSON, is_blacklisted: true }).blocked).toBe(true);
  });

  it('без снимка кружок остаётся пустым, а не ломается', () => {
    // Снимок приходит не от всякой учётной записи: на его месте встают буквы
    // имени, и решает это сам кружок.
    expect(personCandidate({ ...PERSON, avatar: undefined }).avatar).toBe(null);
  });
});
