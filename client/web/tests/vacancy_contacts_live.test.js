// @vitest-environment jsdom
//
// Контакты в карточке вакансии, когда ответ моста приехал уже после выбора
// другой вакансии.
//
// Карточка одна на весь список: ответ о контактах прежней вакансии, отданный
// без сверки номера, встал бы под ту, что открыта теперь.
//
// Своим файлом, а не в `vacancy_card_live.test.js`: добавление зовёт мост
// напрямую, и подменять его приходится на весь файл.

import { afterEach, describe, expect, it, vi } from 'vitest';

import { held } from './bridge_stub.js';
import { settled } from './settled.js';
import { vacancyDetail } from './vacancy_detail.js';

let added = null;

vi.mock('$api/bridge.js', () => ({ call: () => added }));

const { mountVacancyCard } = await import('./vacancy_card_mount.js');

const OWN = [{ id: 1, value: 'hr@first.test' }];
const LATE = { vacancy_id: 7, contacts: [{ id: 5, value: 'late@first.test' }] };

let card = null;

afterEach(() => {
  card?.remove();
  card = null;
  added = null;
});

/** Карточка вакансии №7 с контактом; удаление отвечает обещанием `removed`. */
function screen(removed = null) {
  card = mountVacancyCard((method, payload) =>
    method === 'vacancies.detail'
      ? { vacancy: vacancyDetail(payload, { contacts: payload === 7 ? OWN : [] }) }
      : removed,
  );
  return card;
}

describe('контакты из запоздалого ответа', () => {
  it('ответ о своей вакансии встаёт в карточку', async () => {
    const own = held(LATE);
    const { host } = screen(own.promise);
    await settled();

    host.querySelector('button[title="Удалить контакт"]').click();
    own.give();
    await settled();

    expect(host.textContent).toContain('late@first.test');
  });

  it('удалили контакт и выбрали другую вакансию — ответ прежней не встаёт под новую', async () => {
    const late = held(LATE);
    const { change, host } = screen(late.promise);
    await settled();

    host.querySelector('button[title="Удалить контакт"]').click();
    change('vacancyId', 8);
    await settled();
    late.give();
    await settled();

    expect(host.textContent).not.toContain('late@first.test');
  });

  it('добавили контакт и выбрали другую вакансию — ответ прежней не встаёт под новую', async () => {
    const late = held(LATE);
    added = late.promise;
    const { change, host } = screen();
    await settled();

    host.querySelector('.vac-contacts-head .add-link').click();
    await settled();
    const field = document.querySelector('.modal-dialog input');
    field.value = 'late@first.test';
    field.dispatchEvent(new Event('input', { bubbles: true }));
    await settled();
    field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    change('vacancyId', 8);
    await settled();
    late.give();
    await settled();

    expect(host.textContent).not.toContain('late@first.test');
  });
});
