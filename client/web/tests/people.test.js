// Следствия списков людей: имена, подписи, строка кандидата и заведение.

import { describe, expect, it } from 'vitest';

import {
  blankPerson,
  named,
  personCandidate,
  personHead,
  personLine,
  personName,
  personSub,
  personTitle,
  unreadLine,
} from '../state/people.js';

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

describe('чем подписан человек там, где имени может не быть', () => {
  it('в строке списка ник заменяет имя', () => {
    // Строка списка одна, и ник в ней стоит на месте имени: под ним места нет.
    expect(personTitle({ id: 1, name: '', telegram_username: 'irina_hr' })).toEqual({
      name: '@irina_hr',
      named: true,
    });
  });

  it('в строке списка безымянного зовут прочерком, а не номером', () => {
    // Номер тут не читается никак: строка стоит среди имён, и «Человек #7»
    // человек принимает за имя.
    expect(personTitle({ id: 7, name: '', telegram_username: '' })).toEqual({
      name: '— без имени —',
      named: false,
    });
  });

  it('в шапке карточки ник именем не считается', () => {
    // Ник стоит там своей строкой ниже: поставь его и сверху, человек читал бы
    // одно и то же дважды.
    expect(personHead({ id: 1, name: '', telegram_username: 'irina_hr' })).toEqual({
      name: '— без имени —',
      named: false,
    });
  });

  it('в шапке карточки имя показывают как есть', () => {
    expect(personHead({ id: 1, name: 'Ирина', telegram_username: '' })).toEqual({
      name: 'Ирина',
      named: true,
    });
  });
});

describe('половины подписи человека', () => {
  it('ник и компания названы одними словами со строкой подборщика', () => {
    // Строка списка собирает их сама — по частям, ради собственного вида, — и
    // разойдись слова, один человек читался бы в двух местах как двое.
    const one = { telegram_username: '', last_company_name: null };

    expect(personSub(one)).toEqual({ handle: 'без ника', company: 'без компании' });
    expect(personLine({ ...one, id: 1, name: 'Ирина' }).sub).toBe('без ника · без компании');
  });
});

describe('пустой черновик человека', () => {
  it('пустым он назван быть не может', () => {
    // Форма открывается с ним, и кнопка «Создать» при нём заперта: карточку
    // без имени, ника и номера потом не найти ничем.
    expect(named(blankPerson())).toBe(false);
  });

  it('каждый раз новый', () => {
    // Черновик правят на месте: отдай мы один и тот же, набранное в окне
    // контактов всплыло бы в окне заведения из карточки вакансии.
    const one = blankPerson();
    one.name = 'Ирина';

    expect(blankPerson().name).toBe('');
  });
});
