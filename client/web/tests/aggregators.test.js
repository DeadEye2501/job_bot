// Агрегаторы, переведённые в то, что видно: подписи, переключатели и запор
// действий агента.

import { describe, expect, it } from 'vitest';

import {
  actionBlock,
  aggregatorLastRun,
  aggregatorToggle,
  aggregatorWhere,
  loginMark,
} from '../state/aggregators.js';
import { MASTER_OFF_TITLE } from '../state/sources.js';

const SITE = { id: 2, name: 'Сайт', host: 'example.test', is_web_search: false };
const WEB = { id: 1, name: 'Поиск по сети', host: null, is_web_search: true, is_logged_in: true };

describe('где ищет агрегатор', () => {
  it('у сайта — его адрес', () => {
    expect(aggregatorWhere(SITE)).toBe('example.test');
  });

  it('у поиска по сети адреса нет — сказано, где он ищет', () => {
    // Пустое место под именем читалось бы как недозаведённый агрегатор.
    expect(aggregatorWhere(WEB)).toBe('по всей сети');
  });
});

describe('последний обход', () => {
  it('не было — так и сказано', () => {
    expect(aggregatorLastRun({ ...SITE, last_run_at: null })).toBe('Ещё не обходили');
  });

  it('был — назван временем', () => {
    const note = aggregatorLastRun({ ...SITE, last_run_at: '2026-10-09T12:30:00' });
    expect(note.startsWith('Обход ')).toBe(true);
    expect(note).not.toContain('Ещё не');
  });
});

describe('переключатель агрегатора', () => {
  it('без входа заперт выключенным и объясняет почему', () => {
    // Включённый без входа обещал бы обход, который встанет на первой же
    // странице: сайт не пустит.
    expect(aggregatorToggle({ ...SITE, is_active: true, is_logged_in: false }, true)).toEqual({
      checked: false,
      disabled: true,
      dim: true,
      muted: false,
      title: 'Сначала войдите на сайт',
    });
  });

  it('с входом показывает, как лежит', () => {
    expect(aggregatorToggle({ ...SITE, is_active: true, is_logged_in: true }, true)).toEqual({
      checked: true,
      disabled: false,
      dim: false,
      muted: false,
      title: '',
    });
  });

  it('выключенный приглушён', () => {
    expect(aggregatorToggle({ ...SITE, is_active: false, is_logged_in: true }, true).dim).toBe(true);
  });

  it('из чёрного списка заперт выключенным, и отсев старше входа', () => {
    // Снять запись — единственный путь его включить; «войдите на сайт» в этот
    // миг посылало бы не туда.
    const row = { ...SITE, is_active: true, is_logged_in: false, is_blacklisted: true };
    expect(aggregatorToggle(row, true)).toEqual({
      checked: false,
      disabled: true,
      dim: true,
      muted: false,
      title: 'В чёрном списке — снимите запись, чтобы включить',
    });
  });

  it('при выключенном общем приглушён, но держит своё положение', () => {
    const row = { ...SITE, is_active: true, is_logged_in: true };
    const shown = aggregatorToggle(row, false);
    expect(shown.checked).toBe(true);
    expect(shown.dim).toBe(true);
    expect(shown.muted).toBe(true);
    expect(shown.title).toBe(MASTER_OFF_TITLE);
  });
});

describe('запор действий агента', () => {
  it('отсев старше всего остального', () => {
    // Обход кончится, лампа зажжётся, а запись в отсеве сама не снимется: о
    // ней и надо сказать, чтобы человек знал, что чинить.
    expect(actionBlock({ blocked: true, running: true, lock: 'нет браузера', lockedTip: 'лампа' }))
      .toBe('В чёрном списке — снимите запись, чтобы работать с сайтом');
  });

  it('идущий обход запирает раньше остального', () => {
    // Мост второй прогон не пустит, а «нет браузера» в этот миг сбивало бы:
    // браузер есть, он просто занят.
    expect(actionBlock({ running: true, lock: 'нет браузера', lockedTip: 'лампа' })).toBe('Идёт обход');
  });

  it('без водителя или браузера — слова моста', () => {
    expect(actionBlock({ running: false, lock: 'нет браузера', lockedTip: 'лампа' })).toBe('нет браузера');
  });

  it('при погасшей лампе — её подсказка', () => {
    expect(actionBlock({ running: false, lock: null, lockedTip: 'лампа' })).toBe('лампа');
  });

  it('всё живо — не заперто', () => {
    expect(actionBlock({ running: false, lock: null, lockedTip: '' })).toBe('');
  });
});

describe('значок входа рядом с именем', () => {
  it('говорит, выполнен ли вход, и зовёт войти заново', () => {
    expect(loginMark(false, '')).toEqual({ done: false, icon: 'login', title: 'Войти на сайт' });
    expect(loginMark(true, '')).toEqual({
      done: true,
      icon: 'how_to_reg',
      title: 'Вход выполнен — нажмите, чтобы войти заново',
    });
  });

  it('запертый называет запор, а не вход', () => {
    expect(loginMark(true, 'Идёт обход').title).toBe('Идёт обход');
  });
});
