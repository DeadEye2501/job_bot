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

import { cleanup, render, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import ProfileExperience from '../app/ProfileExperience.svelte';

afterEach(cleanup);

/** Дождаться, пока осядут ответы моста и отрисовка. */
async function settled() {
  for (let i = 0; i < 8; i += 1) {
    await tick();
    await new Promise((done) => setTimeout(done, 0));
  }
}

/** Вкладка с записанными за ней посылками на мост. */
function tab() {
  const sent = [];
  const ask = async (method, payload) => {
    if (method === 'profile.experience') return { experience: [], skills_index: [] };
    if (method === 'profile.save_experience') {
      sent.push(payload.experience);
      return {};
    }
    return {};
  };
  const shown = render(ProfileExperience, { props: { ask } });
  return { sent, q: within(shown.container) };
}

/** Набрать в поле и отпустить его: поля карточки отправляют по уходу фокуса. */
function fill(field, value) {
  field.value = value;
  field.dispatchEvent(new Event('input', { bubbles: true }));
  field.dispatchEvent(new Event('blur', { bubbles: true }));
}

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
});
