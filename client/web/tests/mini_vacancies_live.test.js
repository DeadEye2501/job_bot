// @vitest-environment jsdom
//
// Вакансии в карточках HR, компании, канала и сайта: вакансия другого профиля
// видна серой и не открывается — ни мышью, ни клавишей.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import MiniVacancies from '../components/MiniVacancies.svelte';

afterEach(cleanup);

const row = (id, foreign) => ({
  id,
  title: `Вакансия ${id}`,
  status: 'New',
  score: null,
  created_at: '2026-11-01T10:00:00',
  foreign,
});

function shown() {
  const picked = [];
  render(MiniVacancies, {
    props: { vacancies: [row(1, false), row(2, true)], empty: '', onpick: (id) => picked.push(id) },
  });
  const [mine, theirs] = document.querySelectorAll('.vac-mini-row');
  return { picked, mine, theirs };
}

const enter = (el) => el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

describe('вакансия другого профиля в карточке', () => {
  it('своя открывается, чужая — нет', () => {
    const { picked, mine, theirs } = shown();

    mine.click();
    theirs.click();
    enter(theirs);

    expect(picked).toEqual([1]);
  });

  it('чужая помечена серой, не встаёт в обход клавишей и объясняет почему', () => {
    const { mine, theirs } = shown();

    expect(theirs.classList.contains('mini-row-off')).toBe(true);
    expect(mine.classList.contains('mini-row-off')).toBe(false);
    expect(theirs.getAttribute('tabindex')).toBeNull();
    expect(theirs.getAttribute('role')).toBeNull();
    expect(theirs.title).toBe('Вакансия другого профиля');
  });
});
