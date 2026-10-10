// Следствия каналов: имя в списке, числа воронки, переключатели и запоры.

import { describe, expect, it } from 'vitest';

import { channelName, channelTitle, channelToggle, pollBlock } from '../state/channels.js';
import { MASTER_OFF_TITLE } from '../state/sources.js';

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

  it('канал без ника не приписывает под именем пустоту', () => {
    // Ник приходит не от всякого канала: приватный отдаёт одно название. Собери
    // мы подпись вслепую, под именем стояло бы «@null».
    expect(channelName({ id: 42, title: 'Python Jobs', username: null }))
      .toEqual({ name: 'Python Jobs', handle: '' });
  });

  it('без ника и названия канал назван номером', () => {
    // Такое бывает у приватных каналов: показать нечего, но строка должна
    // остаться нажимаемой.
    expect(channelName({ id: 42, title: '', username: '' }))
      .toEqual({ name: 'Канал #42', handle: '' });
  });
});

describe('переключатель опроса в строке канала', () => {
  const CHANNEL = { is_active: true, is_blacklisted: false };

  it('включённый канал показан включённым', () => {
    expect(channelToggle(CHANNEL, true).checked).toBe(true);
  });

  it('канал из отсева показан выключенным и запертым', () => {
    // Обход его всё равно пропустит: включённый переключатель обещал бы
    // работу, которой не будет.
    const shown = channelToggle({ is_active: true, is_blacklisted: true }, true);
    expect(shown.checked).toBe(false);
    expect(shown.disabled).toBe(true);
  });

  it('запертый переключатель объясняет, чем его отпереть', () => {
    expect(channelToggle({ is_active: true, is_blacklisted: true }, true).title)
      .toBe('В чёрном списке — снимите запись, чтобы включить');
  });

  it('выключенный канал приглушён так же, как отсеянный', () => {
    // Обход не читает ни того ни другого, и выглядеть рабочими они не должны.
    expect(channelToggle({ is_active: false, is_blacklisted: false }, true).dim).toBe(true);
    expect(channelToggle({ is_active: true, is_blacklisted: true }, true).dim).toBe(true);
    expect(channelToggle(CHANNEL, true).dim).toBe(false);
  });
});

describe('строка канала при выключенном общем', () => {
  it('при выключенном общем строка приглушена, но держит своё положение', () => {
    // Обход её не читает — рабочей она выглядеть не должна; а положение своё
    // она хранит, чтобы общий вернул ровно то, что было включено.
    const shown = channelToggle({ is_active: true, is_blacklisted: false }, false);
    expect(shown.checked).toBe(true);
    expect(shown.dim).toBe(true);
  });

  it('при выключенном общем переключатель строки серый и говорит почему', () => {
    // Включённый строчный при выключенном общем обещал бы обход, которого не
    // будет; нажимать его при этом можно — общий вернёт то, что в нём стоит.
    const shown = channelToggle({ is_active: true, is_blacklisted: false }, false);
    expect(shown.muted).toBe(true);
    expect(shown.disabled).toBe(false);
    expect(shown.title).toBe(MASTER_OFF_TITLE);
  });
});

describe('запор ручного прогона канала', () => {
  it('канал в чёрном списке прогнать нельзя, даже когда лампы живы', () => {
    expect(pollBlock({ blacklist_value: '@spam' }, '')).toBe(
      'Канал в чёрном списке — прогнать его нельзя',
    );
  });

  it('отсев старше неживых ламп: сказано про него, а не про них', () => {
    expect(pollBlock({ blacklist_value: '@spam' }, 'Бот заблокирован')).toBe(
      'Канал в чёрном списке — прогнать его нельзя',
    );
  });

  it('чистый канал запирается только лампой', () => {
    expect(pollBlock({ blacklist_value: null }, 'Бот заблокирован')).toBe('Бот заблокирован');
    expect(pollBlock({ blacklist_value: null }, '')).toBe('');
  });

  it('непрочитанная карточка запирается только лампой', () => {
    expect(pollBlock(null, 'Бот заблокирован')).toBe('Бот заблокирован');
  });
});

describe('чем подписан канал в строке списка', () => {
  it('названный канал подписан своим названием', () => {
    // По названию канал узнают: подставь тут ник, человек искал бы в списке не
    // то, что видел в самом Telegram.
    expect(channelTitle({ id: 42, title: 'Python Jobs', username: 'py_jobs' })).toEqual({
      name: 'Python Jobs',
      named: true,
    });
  });

  it('без названия имя берут из ника', () => {
    expect(channelTitle({ id: 42, title: '', username: 'py_jobs' })).toEqual({
      name: '@py_jobs',
      named: true,
    });
  });

  it('совсем безымянный назван прочерком, а не номером', () => {
    // Номером его зовёт шапка карточки — там подпись обязана быть, — а в
    // списке «Канал #42» встал бы в ряд названий и читался бы как название.
    expect(channelTitle({ id: 42, title: '', username: '' })).toEqual({
      name: '— без названия —',
      named: false,
    });
  });
});
