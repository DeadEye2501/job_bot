// @vitest-environment jsdom
//
// Окно подтверждения, которое заперли, пока оно было открыто.
//
// Окно спрашивают до необратимого, а пока человек читает вопрос, мог начаться
// обход: мост такое действие уже не пустит, и кнопка обязана сказать об этом
// сама, а не отказом после нажатия.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import ConfirmDialog from '../components/ConfirmDialog.svelte';
import { settled } from './settled.js';

afterEach(cleanup);

/** Окно с запором `locked`; отдаёт счёт подтверждений и красную кнопку. */
function dialog(locked) {
  const confirmed = [];
  render(ConfirmDialog, {
    props: {
      message: 'Удалить?',
      confirmLabel: 'Удалить',
      locked,
      onconfirm: () => confirmed.push(true),
      oncancel: () => {},
    },
  });
  const button = document.querySelector('.modal-actions .danger');
  return { confirmed, button };
}

describe('запертое окно подтверждения', () => {
  it('кнопка подтверждения неактивна и называет запор', async () => {
    const { button } = dialog('Идёт обход');
    await settled();

    expect(button.disabled).toBe(true);
    expect(button.title).toBe('Идёт обход');
  });

  it('ни нажатие, ни Enter не подтверждают', async () => {
    const { confirmed, button } = dialog('Идёт обход');
    await settled();

    button.click();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await settled();

    expect(confirmed).toEqual([]);
  });

  it('незапертое подтверждается по Enter', async () => {
    const { confirmed } = dialog('');
    await settled();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await settled();

    expect(confirmed).toEqual([true]);
  });
});
