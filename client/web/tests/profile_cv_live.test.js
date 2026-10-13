// @vitest-environment jsdom
//
// Строка файла резюме в анкете: открыть можно только файл, который лежит на
// диске, — иначе система показала бы свою ошибку вместо нашей строки.

import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProfileCv from '../app/ProfileCv.svelte';

afterEach(cleanup);

/** Анкета, у которой мост отдаёт этот файл резюме. */
function sheet(meta) {
  render(ProfileCv, {
    props: {
      ask: async (method) => (method === 'profile.get' ? { cv_meta: meta, profile: null } : null),
    },
  });
}

describe('поле личных предпочтений', () => {
  it('растёт не выше десяти строк, а образование — без предела', async () => {
    // Раскладки в jsdom нет, и высоту не измерить: проверяется, что поле
    // объявило предел, по которому его подгоняет `fitHeight`.
    sheet({ name: 'cv.pdf', size: 2048, exists: true });

    const wishes = await vi.waitFor(() => screen.getByPlaceholderText(/Личные предпочтения/));
    const education = screen.getAllByRole('textbox').find((one) => one !== wishes && one.tagName === 'TEXTAREA');

    expect(wishes.dataset.lines).toBe('10');
    expect(education.dataset.lines).toBeUndefined();
  });
});

describe('файл резюме в анкете', () => {
  it('пропавший с диска не открывается', async () => {
    sheet({ name: 'cv.pdf', size: 2048, exists: false });

    const open = await vi.waitFor(() => screen.getByRole('button', { name: 'Открыть' }));

    expect(open.disabled).toBe(true);
  });

  it('лежащий на диске открывается', async () => {
    sheet({ name: 'cv.pdf', size: 2048, exists: true });

    const open = await vi.waitFor(() => screen.getByRole('button', { name: 'Открыть' }));

    expect(open.disabled).toBe(false);
  });
});
