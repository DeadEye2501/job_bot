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
