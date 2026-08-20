// Следствия каналов: имя в списке, числа воронки, переключатели и запоры.

import { describe, expect, it } from 'vitest';

import {
  channelName,
  channelStats,
  channelTitle,
  channelToggle,
  channelsToggle,
  pollBlock,
} from '../state/channels.js';

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
