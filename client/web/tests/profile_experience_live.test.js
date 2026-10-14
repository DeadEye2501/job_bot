// @vitest-environment jsdom
//
// Отметка «эта строка уже уехала» у вкладки мест работы.
//
// Номера свежим карточкам даёт мост, а вкладка себя после записи не
// перечитывает — по одному лишь номеру заведённая в этот заход строка до конца
// визита считалась «свежей». Опустошив у неё обязательное поле, человек
// вычёркивал её из посылки, а мост, заменяющий перечень целиком, стирал её
// молча вместе с достижениями и стеком.
//
// Само правило отбора сторожат проверки состояния (`experience.test.js`); здесь
// предмет другой — что метку кто-то ставит, и ставит после удачи.

import { cleanup } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import ExperienceCard from '../components/ExperienceCard.svelte';
import { EXPERIENCE } from '../state/experience.js';
import { fill, recordsTab } from './records_tab.js';
import { settled } from './settled.js';

afterEach(cleanup);

const tab = () => recordsTab(EXPERIENCE, ExperienceCard);

/** Завести место работы и заполнить три обязательных поля. */
async function fillFresh(q) {
  q.getByText('+ Добавить место работы').click();
  await settled();
  fill(q.getByPlaceholderText('Компания'), 'Контур');
  await settled();
  fill(q.getByPlaceholderText('Должность'), 'Python-разработчик');
  await settled();
  // Дата набирается прямо в поле подборщика: календарь для этого не нужен.
  fill(q.getAllByPlaceholderText('дд.мм.гггг')[0], '01.03.2020');
  await settled();
}

describe('живая вкладка мест работы', () => {
  it('уехавшую карточку больше не считает свежей и опустошённой не стирает', async () => {
    const { sent, q } = tab();
    await settled();
    await fillFresh(q);

    expect(sent.at(-1)).toHaveLength(1);

    // Человек передумал формулировку и стёр должность.
    fill(q.getByPlaceholderText('Должность'), '');
    await settled();

    // Пустой посылки быть не должно: она стёрла бы уже записанное.
    expect(sent.at(-1)).not.toHaveLength(0);
  });

  it('начатую карточку без даты начала не сохраняет, говорит об этом и метит пустые поля', async () => {
    const { sent, q } = tab();
    await settled();
    q.getByText('+ Добавить место работы').click();
    await settled();

    fill(q.getByPlaceholderText('Компания'), 'Контур');
    await settled();

    expect(sent.at(-1)).toEqual([]);
    expect(q.getByText(/Место работы #1/)).toBeTruthy();
    expect(q.getByPlaceholderText('Должность').classList.contains('missing')).toBe(true);
    expect(q.getAllByPlaceholderText('дд.мм.гггг')[0].classList.contains('missing')).toBe(true);
    expect(q.getByPlaceholderText('Компания').classList.contains('missing')).toBe(false);
  });
});
