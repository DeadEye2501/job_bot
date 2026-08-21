// @vitest-environment jsdom
//
// Каким цветом карточка вакансии просит подтверждения.
//
// Окно подтверждения заводилось для необратимого и красило кнопку красным
// литералом, а зовут его из карточки дважды: удалить вакансию и отправить
// отклик. Красная «Отправить» читается как «Удалить».

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import VacancyCard from '../app/VacancyCard.svelte';
import { settled } from './settled.js';
import { vacancyDetail } from './vacancy_detail.js';

afterEach(cleanup);

/** Карточка с привязанным HR: без него пункт отправки заперт. */
function card() {
  const shown = render(VacancyCard, {
    props: {
      ask: async () => ({ vacancy: vacancyDetail(7, { hr: { id: 3, name: 'Аня' } }) }),
      say: () => {},
      events: { on: () => () => {} },
      lockedTip: '',
      vacancyId: 7,
      oncontacts: () => {},
      onclose: () => {},
      onchanged: () => {},
    },
  });
  return shown.container;
}

/** Нажать кнопку с такой подписью. */
function press(where, label) {
  const found = [...where.querySelectorAll('button')].find((one) =>
    one.textContent.includes(label),
  );
  found.click();
  return found;
}

/** Поднять окно подтверждения пунктом меню действий. */
async function ask(where, item) {
  where.querySelector('button[title="Действия"]').click();
  await settled();
  press(where, item);
  await settled();
}

describe('окно подтверждения из карточки вакансии', () => {
  it('отправку отклика подтверждают залитой акцентом кнопкой, а не красной', async () => {
    const where = card();
    await settled();

    await ask(where, 'Отправить отклик');

    const confirm = [...where.querySelectorAll('.modal-actions button')].at(-1);
    expect(confirm.textContent).toContain('Отправить');
    expect(confirm.className).toContain('primary');
    expect(confirm.className).not.toContain('danger');
  });

  it('удаление вакансии остаётся красным', async () => {
    const where = card();
    await settled();

    await ask(where, 'Удалить');

    const confirm = [...where.querySelectorAll('.modal-actions button')].at(-1);
    expect(confirm.textContent).toContain('Удалить');
    expect(confirm.className).toContain('danger');
  });
});
