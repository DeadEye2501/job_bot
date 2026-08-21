// @vitest-environment jsdom
//
// Заведение человека из списка контактов: одно нажатие — одна карточка.
//
// Заслон от второго нажатия стоял только у копии этой же формы в подборщике
// при вакансии, своим `if (saving) return`, а у списка контактов его не было
// вовсе. Сторожа на одинаковое имя нет ни в базе, ни на мосту — `hr.create`
// отбивает только занятый номер учётной записи, — и два нажатия «Создать»
// подряд заводили двух людей.
//
// Договор самого окна стережёт `ask_dialog_live.test.js`; здесь предмет
// другой — проводка: признак взводится **до** зова моста и гасится после.

import { cleanup, render, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import PeopleList from '../app/PeopleList.svelte';

afterEach(cleanup);

/** Дождаться, пока осядут ответы моста и отрисовка. */
async function settled() {
  for (let i = 0; i < 6; i += 1) {
    await tick();
    await new Promise((done) => setTimeout(done, 0));
  }
}

/** Вкладка «HR» с мостом, отвечающим не раньше, чем ему позволят. */
function tab() {
  const asked = [];
  let letGo;
  const flying = new Promise((done) => {
    letGo = done;
  });
  const ask = async (method, payload) => {
    asked.push({ method, payload });
    if (method === 'hr.create') {
      await flying;
      return { id: 1 };
    }
    return { hrs: [], has_more: false };
  };

  const shown = render(PeopleList, {
    props: {
      ask,
      say: () => {},
      events: { on: () => () => {} },
      open: null,
      onopened: () => {},
      oncompany: () => {},
      onvacancy: () => {},
    },
  });
  return { asked, letGo, q: within(shown.container) };
}

describe('живая вкладка «HR»', () => {
  it('второе нажатие «Создать», пока летит первое, второй карточки не заводит', async () => {
    const { asked, letGo, q } = tab();
    await settled();

    q.getByTitle('Добавить HR').click();
    await settled();
    const name = q.getByPlaceholderText('Имя');
    name.value = 'Мария';
    name.dispatchEvent(new Event('input', { bubbles: true }));
    await settled();

    const create = q.getByText('Создать');
    create.click();
    await settled();
    create.click();
    await settled();
    letGo();
    await settled();

    expect(asked.filter((one) => one.method === 'hr.create')).toHaveLength(1);
  });
});
