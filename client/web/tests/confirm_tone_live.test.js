// @vitest-environment jsdom
//
// Каким цветом карточка вакансии просит подтверждения.
//
// Окно подтверждения зовут для необратимого, и кнопка его красная: удаление
// вакансии — последнее, что может остановить руку.

import { afterEach, describe, expect, it } from 'vitest';

import { settled } from './settled.js';
import { mountVacancyCard, openActions, press } from './vacancy_card_mount.js';
import { vacancyDetail } from './vacancy_detail.js';

let card = null;

afterEach(() => {
  card?.remove();
  card = null;
});

describe('окно подтверждения из карточки вакансии', () => {
  it('удаление вакансии остаётся красным', async () => {
    card = mountVacancyCard((method, payload) => ({ vacancy: vacancyDetail(payload) }));
    await settled();

    openActions(card.host);
    press('Удалить');
    await settled();

    const confirm = [...document.querySelectorAll('.modal-actions button')].at(-1);
    expect(confirm.textContent).toContain('Удалить');
    expect(confirm.className).toContain('danger');
  });
});
