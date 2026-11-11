// @vitest-environment jsdom
//
// Вкладка Letters: четыре письма профиля — пара на языке приложения над чертой, английская
// под ней — и запись набранного.

import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProfileLetters from '../app/ProfileLetters.svelte';
import ProfileScreen from '../app/ProfileScreen.svelte';
import { settled } from './settled.js';

afterEach(cleanup);

const PLACEHOLDERS = [
  'Полное сопроводительное письмо',
  'Короткое сопроводительное письмо',
  'Full cover letter',
  'Short cover letter',
];

/** Вкладка, которой мост отдаёт эти письма и предел короткого; ответ — что у
 *  моста спрашивали. */
function letters(stored, shortMax = 1024) {
  const asked = [];
  render(ProfileLetters, {
    props: {
      ask: async (method, payload) => {
        asked.push([method, payload]);
        return method === 'profile.letters' ? { letters: stored, short_max: shortMax } : {};
      },
    },
  });
  return asked;
}

const EMPTY = { app: null, app_short: null, en: null, en_short: null };

function typeInto(field, text) {
  field.value = text;
  field.dispatchEvent(new Event('input', { bubbles: true }));
  field.dispatchEvent(new Event('blur'));
}

describe('вкладка Letters', () => {
  it('стоит между CV и Skills', () => {
    render(ProfileScreen, { props: { ask: async () => null, tab: 'cv', ontab: () => {} } });

    const tabs = [...document.querySelectorAll('.top-tabs .tab')].map((one) => one.textContent.trim());

    expect(tabs.slice(0, 3)).toEqual(['CV', 'Letters', 'Skills']);
  });

  it('показывает записанные письма: пара на языке приложения над чертой, английская под ней', async () => {
    letters({ app: 'Здравствуйте', app_short: 'Коротко', en: 'Hello', en_short: null });
    await vi.waitFor(() => screen.getByPlaceholderText('Full cover letter'));

    const order = [...document.querySelector('.letters').children].map(
      (one) => one.placeholder ?? 'черта',
    );

    expect(order).toEqual([PLACEHOLDERS[0], PLACEHOLDERS[1], 'черта', PLACEHOLDERS[2], PLACEHOLDERS[3]]);
    expect(PLACEHOLDERS.map((one) => screen.getByPlaceholderText(one).value)).toEqual([
      'Здравствуйте',
      'Коротко',
      'Hello',
      '',
    ]);
  });

  it('набранное уезжает на мост всеми четырьмя письмами', async () => {
    const asked = letters({ ...EMPTY, app: 'Здравствуйте' });
    await vi.waitFor(() => screen.getByPlaceholderText('Short cover letter'));

    typeInto(screen.getByPlaceholderText('Short cover letter'), 'Short');
    await settled();

    expect(asked.filter(([method]) => method === 'profile.save_letters').at(-1)[1]).toEqual({
      app: 'Здравствуйте',
      app_short: '',
      en: '',
      en_short: 'Short',
    });
  });

  it('короткое письмо не длиннее предела, названного мостом; полное — своего', async () => {
    letters(EMPTY, 700);
    await vi.waitFor(() => screen.getByPlaceholderText('Short cover letter'));

    expect(PLACEHOLDERS.map((one) => screen.getByPlaceholderText(one).maxLength)).toEqual([4000, 700, 4000, 700]);
  });

  it('письма, набранные теми же, что записаны, заново не записываются', async () => {
    const asked = letters({ ...EMPTY, en: 'Hello' });
    await vi.waitFor(() => screen.getByPlaceholderText('Full cover letter'));

    typeInto(screen.getByPlaceholderText('Full cover letter'), 'Hello ');
    await settled();

    expect(asked.some(([method]) => method === 'profile.save_letters')).toBe(false);
  });
});
