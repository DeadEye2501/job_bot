// @vitest-environment jsdom
//
// Окно подтверждения отправки: откликатель ждёт человека перед каждой
// отправкой, окно показывает, что уйдёт, и отдаёт правку или «Закончить».

import { cleanup } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import { bar } from './bottom_bar_stub.js';
import { buttonBy } from './press.js';
import { settled } from './settled.js';

afterEach(cleanup);

const LINK = 'https://t.me/jobs/42';

function items() {
  return [
    { label: '', kind: 'text', value: 'Здравствуйте', error: '', selector: '' },
    { label: 'Имя', kind: 'text', value: 'Иван', error: 'Только латиница', selector: '#name' },
    { label: 'Город', kind: 'choice', value: 'Москва', error: '', selector: '#city' },
    { label: 'Согласие', kind: 'check', value: 'true', error: '', selector: '#agree' },
    { label: 'Отчество', kind: 'text', value: '', error: '', selector: '#patronymic' },
  ];
}

/** Полоса, ждущая подтверждения: прогон идёт, пришла весть с пунктами. */
async function waiting(asked = items()) {
  const shown = bar({ db: true, tg: true, chat: true, embed: true });
  await settled();
  shown.handlers.ingestion_started();
  shown.handlers.human_needed({ kind: 'confirm', host: '', payload: { url: LINK, items: asked } });
  await settled();
  return shown;
}

const dialog = () => document.querySelector('.confirm-send');
const fields = () => [...dialog().querySelectorAll('.confirm-item')];
const button = (text) => buttonBy(text, { exact: true });
const answered = (asked) => asked.filter((one) => one.method === 'system.human_done').map((one) => one.payload);

function type(field, text) {
  const input = field.querySelector('textarea, input');
  input.value = text;
  input.dispatchEvent(new Event('input', { bubbles: true }));
}

describe('окно подтверждения отправки', () => {
  it('весть с пунктами открывает окно: ссылка на вакансию сверху, пункты ниже', async () => {
    await waiting();

    const link = dialog().querySelector('.confirm-send-link');
    expect(link.textContent).toContain(LINK);
    expect(link.compareDocumentPosition(fields()[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(fields()).toHaveLength(5);
  });

  it('пункты по видам: письмо без подписи, поле, список текстом, галочка', async () => {
    await waiting();
    const [letter, name, city, agree] = fields();

    expect(letter.querySelector('.confirm-item-label')).toBeNull();
    expect(letter.querySelector('textarea').value).toBe('Здравствуйте');
    expect(name.querySelector('.confirm-item-label').textContent.trim()).toBe('Имя');
    expect(city.querySelector('textarea, input').value).toBe('Москва');
    expect(agree.querySelector('input[type="checkbox"]').checked).toBe(true);
  });

  it('пункт с ошибкой сайта подсвечен и показывает её текст', async () => {
    await waiting();
    const name = fields()[1];

    expect(name.querySelector('textarea').classList.contains('missing')).toBe(true);
    expect(name.querySelector('.modal-error').textContent).toBe('Только латиница');
    expect(fields()[0].querySelector('textarea').classList.contains('missing')).toBe(false);
  });

  it('«Подтвердить» отдаёт то, что в окне сейчас; пустой пункт уходит пустым', async () => {
    const { asked } = await waiting();

    type(fields()[1], 'Ivan');
    fields()[3].querySelector('input[type="checkbox"]').click();
    button('Подтвердить').click();
    await settled();

    const [answer] = answered(asked);
    expect(answer.items.map((one) => one.value)).toEqual(['Здравствуйте', 'Ivan', 'Москва', 'false', '']);
    expect(answer.items[1].selector).toBe('#name');
  });

  it('ответ гасит окно и плашку сразу: второе нажатие в следующее ожидание не уходит', async () => {
    const { asked } = await waiting();

    const confirm = button('Подтвердить');
    confirm.click();
    await settled();
    confirm.click();
    await settled();

    expect(answered(asked)).toHaveLength(1);
    expect(dialog()).toBeNull();
    expect(document.querySelector('.human-plate')).toBeNull();
  });

  it('обязательный пункт помечен у подписи', async () => {
    await waiting([{ label: 'Имя', kind: 'text', value: '', error: '', selector: '#n', required: true }]);

    expect(fields()[0].querySelector('.confirm-item-required')).not.toBeNull();
  });

  it('пока обязательное пусто, подтвердить нельзя ни в окне, ни с плашки', async () => {
    const { asked } = await waiting([
      { label: 'Имя', kind: 'text', value: '', error: '', selector: '#n', required: true },
      { label: 'Согласие', kind: 'check', value: 'false', error: '', selector: '#a', required: true },
    ]);
    expect(button('Подтвердить').disabled).toBe(true);

    type(fields()[0], 'Иван');
    await settled();
    expect(button('Подтвердить').disabled).toBe(true);

    fields()[1].querySelector('input[type="checkbox"]').click();
    await settled();
    expect(button('Подтвердить').disabled).toBe(false);

    type(fields()[0], '');
    button('Свернуть').click();
    await settled();
    expect(document.querySelector('.human-plate-done').disabled).toBe(true);
    expect(answered(asked)).toEqual([]);
  });

  it('«Закончить» уходит признаком', async () => {
    const { asked } = await waiting();

    button('Закончить').click();
    await settled();

    expect(answered(asked)).toEqual([{ drop: true }]);
  });

  it('окно сворачивается в плашку и разворачивается из неё: вместе их не бывает', async () => {
    await waiting();
    expect(document.querySelector('.human-plate')).toBeNull();

    button('Свернуть').click();
    await settled();
    expect(dialog()).toBeNull();
    expect(document.querySelector('.human-plate').textContent).toContain('Требуется подтверждение ввода');

    document.querySelector('.human-plate-text').click();
    await settled();
    expect(dialog()).not.toBeNull();
    expect(document.querySelector('.human-plate')).toBeNull();
  });

  it('галочка плашки подтверждает то, что сейчас в окне', async () => {
    const { asked } = await waiting();
    type(fields()[1], 'Ivan');
    button('Свернуть').click();
    await settled();

    document.querySelector('.human-plate-done').click();
    await settled();

    expect(answered(asked)[0].items[1].value).toBe('Ivan');
  });

  it('капча — прежняя плашка без окна', async () => {
    const { asked, handlers } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();
    handlers.ingestion_started();
    handlers.human_needed({ kind: 'captcha', host: 'site.test', payload: null });
    await settled();

    expect(dialog()).toBeNull();
    document.querySelector('.human-plate-text').click();
    await settled();
    expect(asked.map((one) => one.method)).toContain('system.reveal_browser');
  });
});
