// @vitest-environment jsdom
//
// Отклик из карточки вакансии: один способ уходит сразу, из нескольких
// выбирают в окне.

import { flushSync } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import { hearRound } from '../state/round.svelte.js';
import { held, roundGoes } from './bridge_stub.js';
import { press } from './press.js';
import { settled } from './settled.js';
import { mountVacancyCard, openActions } from './vacancy_card_mount.js';
import { vacancyDetail } from './vacancy_detail.js';

const HR = { id: 1, name: 'Иван', telegram_username: 'ivan' };
const MAIL = { method: 'email', target: 'hr@example.com' };
const FORM = { method: 'form', target: 'https://example.com/job' };

let card = null;

afterEach(() => {
  hearRound({ on: () => () => {} });
  card?.remove();
  card = null;
});

/** Карточка, у которой мост отдаёт эти способы; `ways` может быть обещанием. */
function screen(ways, telegram) {
  card = mountVacancyCard((method, payload) => {
    if (method === 'vacancies.detail') {
      return { vacancy: vacancyDetail(payload, { hr: telegram ? HR : null }) };
    }
    if (method === 'vacancies.apply_ways') {
      return Promise.resolve(ways).then((found) => ({ ways: found, telegram, lock: null }));
    }
    return { ok: true };
  });
  return card;
}


async function respond() {
  await settled();
  openActions(card.host);
  press('Откликнуться');
  await settled();
}

/** Ушедшие отклики — зовом и нагрузкой. */
const sent = (asked) =>
  asked
    .filter(({ method }) => method === 'vacancies.apply_via' || method === 'vacancies.send_application')
    .map(({ method, payload }) => [method, payload]);

describe('отклик из карточки', () => {
  it('единственный способ уходит сразу, без окна выбора', async () => {
    const { asked } = screen([MAIL], false);
    await respond();

    expect(document.querySelector('.way-row')).toBeNull();
    expect(sent(asked)).toEqual([
      ['vacancies.apply_via', { vacancy_id: 7, method: 'email', target: 'hr@example.com' }],
    ]);
  });

  it('единственный Telegram уходит прежней отправкой', async () => {
    const { asked } = screen([], true);
    await respond();

    expect(sent(asked)).toEqual([['vacancies.send_application', { vacancy_id: 7 }]]);
  });

  it('из нескольких способов выбирают в окне, и уходит выбранный', async () => {
    const { asked } = screen([FORM, MAIL], true);
    await respond();

    const rows = document.querySelectorAll('.way-row');
    expect(rows).toHaveLength(3);
    expect(sent(asked)).toEqual([]);

    rows[2].click();
    flushSync();
    press('Подтвердить');
    await settled();

    expect(sent(asked)).toEqual([
      ['vacancies.apply_via', { vacancy_id: 7, method: 'email', target: 'hr@example.com' }],
    ]);
    expect(document.querySelector('.way-row')).toBeNull();
  });

  it('пока ничего не выбрано, подтверждать нечего', async () => {
    const { asked } = screen([FORM, MAIL], true);
    await respond();

    press('Подтвердить');
    await settled();

    expect(sent(asked)).toEqual([]);
  });

  it('выбрали другую вакансию, пока мост искал способы, — отклик не уходит никуда', async () => {
    // Панель одна на весь список: ответ о способах прежней вакансии пришёл бы
    // уже к новой, и Telegram ушёл бы по ней сразу и без вопроса.
    const late = held();
    const { asked, change } = screen(late.promise, true);
    await respond();

    change('vacancyId', 8);
    await settled();
    late.give([]);
    await settled();

    expect(sent(asked)).toEqual([]);
  });

  it('окно, открытое до обхода, запирает подтверждение, когда обход начался', async () => {
    const { asked } = screen([FORM, MAIL], true);
    await respond();
    document.querySelectorAll('.way-row')[2].click();
    flushSync();

    roundGoes();
    flushSync();
    press('Подтвердить');
    await settled();

    expect(sent(asked)).toEqual([]);
  });

  it('во время обхода отклик заперт целиком, и об этом сказано', async () => {
    roundGoes();
    const { asked, said } = screen([FORM, MAIL], true);
    await respond();

    expect(asked.map((one) => one.method)).not.toContain('vacancies.apply_ways');
    expect(sent(asked)).toEqual([]);
    expect(said).toContain('Идёт обход');
  });
});
