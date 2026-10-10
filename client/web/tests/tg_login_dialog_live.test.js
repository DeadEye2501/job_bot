// @vitest-environment jsdom
//
// Облачный пароль Telegram в окне входа: скрыт точками, глазом показывается, и
// уходит набранное.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import TgLoginDialog from '../components/TgLoginDialog.svelte';
import { press } from './press.js';
import { settled } from './settled.js';

afterEach(cleanup);

function dialog() {
  const sent = [];
  render(TgLoginDialog, {
    props: {
      step: 'password',
      phone: '+70000000000',
      relogin: false,
      busy: false,
      error: '',
      onsubmit: (value) => sent.push(value),
      oncancel: () => {},
    },
  });
  return { sent, field: () => document.querySelector('input[placeholder="Облачный пароль"]') };
}

describe('облачный пароль в окне входа', () => {
  it('скрыт точками и показывается глазом', async () => {
    const { field } = dialog();
    expect(field().type).toBe('password');

    document.querySelector('button[title="Показать"]').click();
    await settled();

    expect(field().type).toBe('text');
  });

  it('уходит набранное', async () => {
    const { sent, field } = dialog();

    field().value = 'secret';
    field().dispatchEvent(new Event('blur'));
    await settled();
    press('Войти');

    expect(sent).toEqual(['secret']);
  });
});
