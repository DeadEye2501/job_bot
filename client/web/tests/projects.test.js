// Следствия вкладки проектов: что уезжает на мост и чем подписана карточка.

import { describe, expect, it } from 'vitest';

import { projectReady, projectsGoing, projectTitle } from '../state/projects.js';

describe('какие проекты уезжают на мост', () => {
  it('проект с названием уезжает', () => {
    expect(projectReady({ name: 'Бот' })).toBe(true);
  });

  it('без названия не уезжает', () => {
    expect(projectReady({ name: '   ' })).toBe(false);
  });
});

describe('что из перечня проектов уезжает на мост', () => {
  const FRESH = { id: null, name: '' };
  const FILLED = { id: 3, name: 'Бот' };

  it('свежий пустой не уезжает и записи соседей не отменяет', () => {
    expect(projectsGoing([FRESH, FILLED])).toEqual({ going: [FILLED], trouble: '' });
  });

  it('записанный, оставшийся без названия, назван своим номером', () => {
    const emptied = { ...FILLED, name: '' };

    expect(projectsGoing([FRESH, emptied]).trouble).toContain('Проект #2');
  });
});

describe('подпись свёрнутой карточки проекта', () => {
  it('только название — ни должности, ни периода', () => {
    expect(projectTitle({ name: 'Бот' })).toEqual({ name: 'Бот', role: '', period: '' });
  });

  it('безымянный назван прямо', () => {
    expect(projectTitle({ name: '' }).name).toBe('Без названия');
  });
});
