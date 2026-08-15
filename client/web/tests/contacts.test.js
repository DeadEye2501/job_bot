// Следствия списков контактов: отбор, отметки и слова.

import { describe, expect, it } from 'vitest';

import {
  BLACKLIST_KINDS,
  blacklistCounts,
  blacklistHints,
  blacklistShown,
  channelName,
  channelStats,
  channelToggle,
  channelsToggle,
  fresher,
  initials,
  linkReady,
  named,
  personCandidate,
  personLine,
  personName,
  unreadLine,
  valueField,
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
      .toBe('Нет существующих hr');
    expect(blacklistHints({
      items: ITEMS,
      rows: ITEMS.map((one) => ({ kind: 'hr', value: one.value })),
      kind: 'hr',
      typed: '',
    }).empty).toBe('Все уже в blacklist');
    expect(blacklistHints({ items: ITEMS, rows: [], kind: 'hr', typed: 'зз' }).empty)
      .toBe('Ничего не найдено');
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

describe('статистика канала', () => {
  const STATS = {
    total: 12,
    vacancies_per_day: 1.5,
    fit_percent: 40,
    apply_percent: 25,
    response_percent: null,
  };

  it('канал без собранного показывает пустую статистику', () => {
    // Нули в столбиках читаются как «собрали и ничего не нашли», а пустое
    // состояние говорит «ещё не обходили».
    expect(channelStats({ ...STATS, total: 0 }).empty).toBe(true);
  });

  it('канал с собранным показывает воронку', () => {
    expect(channelStats(STATS).empty).toBe(false);
  });

  it('известная доля названа процентом', () => {
    expect(channelStats(STATS).fit).toBe('40%');
  });

  it('неизвестная доля названа прочерком', () => {
    // Ноль процентов и «не из чего считать» — разные вещи: у канала без
    // откликов доля ответов не ноль, её просто нет.
    expect(channelStats(STATS).response).toBe('—');
  });
});

describe('переключатель опроса в строке канала', () => {
  const CHANNEL = { is_active: true, is_blacklisted: false };

  it('включённый канал показан включённым', () => {
    expect(channelToggle(CHANNEL).checked).toBe(true);
  });

  it('канал из отсева показан выключенным и запертым', () => {
    // Обход его всё равно пропустит: включённый переключатель обещал бы
    // работу, которой не будет.
    const shown = channelToggle({ is_active: true, is_blacklisted: true });
    expect(shown.checked).toBe(false);
    expect(shown.disabled).toBe(true);
  });

  it('запертый переключатель объясняет, чем его отпереть', () => {
    expect(channelToggle({ is_active: true, is_blacklisted: true }).title)
      .toBe('В blacklist — снимите запись, чтобы включить');
  });

  it('выключенный канал приглушён так же, как отсеянный', () => {
    // Обход не читает ни того ни другого, и выглядеть рабочими они не должны.
    expect(channelToggle({ is_active: false, is_blacklisted: false }).dim).toBe(true);
    expect(channelToggle({ is_active: true, is_blacklisted: true }).dim).toBe(true);
    expect(channelToggle(CHANNEL).dim).toBe(false);
  });
});

describe('общий переключатель над списком каналов', () => {
  const ON = { is_active: true, is_blacklisted: false };
  const OFF = { is_active: false, is_blacklisted: false };
  const BLOCKED = { is_active: false, is_blacklisted: true };

  it('когда включены все, нажатие выключает все', () => {
    const shown = channelsToggle([ON, ON]);
    expect(shown.checked).toBe(true);
    expect(shown.title).toBe('Выключить все каналы');
  });

  it('когда включены не все, нажатие включает все', () => {
    const shown = channelsToggle([ON, OFF]);
    expect(shown.checked).toBe(false);
    expect(shown.title).toBe('Включить все каналы');
  });

  it('отсеянные каналы в счёт не идут', () => {
    // Их не трогает и сам обход: считай их выключенными — общий переключатель
    // никогда не сошёлся бы с тем, что видно в строках.
    expect(channelsToggle([ON, BLOCKED]).checked).toBe(true);
  });

  it('пустой список запирает переключатель', () => {
    const shown = channelsToggle([]);
    expect(shown.disabled).toBe(true);
    expect(shown.title).toBe('Пока нет каналов');
  });

  it('список из одних отсеянных запирает и говорит почему', () => {
    const shown = channelsToggle([BLOCKED]);
    expect(shown.disabled).toBe(true);
    expect(shown.title).toBe('Все каналы в blacklist');
  });
});
