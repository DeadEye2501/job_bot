// @vitest-environment jsdom
//
// Скрининг из карточки вакансии: окно диалогом, а без скрининга пункт не
// нажимается.

import { afterEach, describe, expect, it } from 'vitest';

import { held } from './bridge_stub.js';
import { buttonBy } from './press.js';
import { settled } from './settled.js';
import { mountVacancyCard, openActions } from './vacancy_card_mount.js';
import { vacancyDetail } from './vacancy_detail.js';

const SCREENING = {
  applications: [
    {
      target: 'hr@example.com',
      lines: [
        { from_us: false, text: 'Сколько лет опыта?' },
        { from_us: true, text: 'Пять' },
      ],
    },
  ],
};

let card = null;

afterEach(() => {
  card?.remove();
  card = null;
});

/** Карточка со скринингом или без; `screening` может быть обещанием. */
function screen(hasScreening, screening = SCREENING) {
  card = mountVacancyCard((method, payload) =>
    method === 'vacancies.detail'
      ? { vacancy: vacancyDetail(payload, { has_screening: hasScreening }) }
      : screening,
  );
  return card;
}

async function screeningItem() {
  await settled();
  openActions(card.host);
  return buttonBy('Скрининг', { among: '.menu-item' });
}

describe('скрининг из карточки', () => {
  it('стоит в меню между исходным текстом и переходом к источнику', async () => {
    screen(true);
    await screeningItem();

    const labels = [...document.querySelectorAll('.menu-item')].map((one) => one.textContent);
    const at = labels.findIndex((one) => one.includes('Скрининг'));
    expect(labels[at - 1]).toContain('Открыть raw_text');
    expect(labels[at + 1]).toContain('Перейти к источнику');
  });

  it('без скрининга пункт серый и не нажимается', async () => {
    const { asked } = screen(false);
    const item = await screeningItem();

    expect(item.disabled).toBe(true);
    expect(item.classList.contains('blocked')).toBe(true);
    item.click();
    await settled();
    expect(asked.map((one) => one.method)).not.toContain('vacancies.screening');
  });

  it('открывает окно, где реплики стоят диалогом: наши справа, работодателя слева', async () => {
    const { asked } = screen(true);
    (await screeningItem()).click();
    await settled();

    expect(asked).toContainEqual({ method: 'vacancies.screening', payload: 7 });
    const bubbles = [...document.querySelectorAll('.modal-dialog .cnt-bubble')];
    expect(bubbles.map((one) => [one.textContent.trim(), one.classList.contains('me')])).toEqual([
      ['Сколько лет опыта?', false],
      ['Пять', true],
    ]);
  });

  it('выбрали другую вакансию, пока скрининг ехал, — окно прежней не открывается', async () => {
    const late = held();
    const { change } = screen(true, late.promise);
    (await screeningItem()).click();

    change('vacancyId', 8);
    await settled();
    late.give(SCREENING);
    await settled();

    expect(document.querySelector('.modal-dialog .cnt-bubble')).toBeNull();
  });
});
