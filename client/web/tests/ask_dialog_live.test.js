// @vitest-environment jsdom
//
// Запор основной кнопки спрашивающего окна на время ответа моста.
//
// Заслон стоял только у копии этой же формы в карточке вакансии — своим
// `if (saving) return` в обработчике, — а у самого окна его не было вовсе.
// Два нажатия «Создать» подряд заводили две карточки: сторожа на одинаковое имя
// нет ни в базе, ни на мосту.

import { cleanup, render, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import AskDialog from '../components/AskDialog.svelte';

afterEach(cleanup);

/** Окно с записанным за ним следом нажатий. */
function dialog(busy) {
  const trail = [];
  const shown = render(AskDialog, {
    props: {
      icon: 'person_add',
      title: 'Новый человек',
      confirmLabel: 'Создать',
      busyLabel: 'Завожу…',
      busy,
      ready: true,
      onconfirm: () => trail.push('заведение начато'),
      oncancel: () => trail.push('окно закрыто'),
      children: () => {},
    },
  });
  const buttons = within(shown.container).getAllByRole('button');
  return { trail, confirm: buttons[buttons.length - 1] };
}

describe('живое спрашивающее окно', () => {
  it('на время работы не пускает второе нажатие и говорит, что работа идёт', () => {
    const { trail, confirm } = dialog(true);

    confirm.click();

    expect(trail).toEqual([]);
    expect(confirm.textContent).toContain('Завожу…');
  });

  it('свободное окно нажатие пропускает', () => {
    const { trail, confirm } = dialog(false);

    confirm.click();

    expect(trail).toEqual(['заведение начато']);
    expect(confirm.textContent).toContain('Создать');
  });
});
