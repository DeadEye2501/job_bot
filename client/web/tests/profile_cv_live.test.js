// @vitest-environment jsdom
//
// Строка файла резюме в анкете: открыть можно только файл, который лежит на
// диске, — иначе система показала бы свою ошибку вместо нашей строки.

import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { settled } from './settled.js';

const saved = [];

vi.mock('$api/bridge.js', () => ({
  call: (method, payload) => {
    if (method === 'profile.save') saved.push(payload);
    return Promise.resolve({});
  },
}));

const { default: ProfileCv } = await import('../app/ProfileCv.svelte');

afterEach(() => {
  saved.length = 0;
  cleanup();
});

/** Анкета, у которой мост отдаёт этот файл резюме и это фото. */
function sheet(meta, photo = null) {
  const asked = [];
  let photoUrl = photo;
  const answers = {
    'profile.pick_photo': () => ({ image: PICKED }),
    'profile.clear_photo': () => {
      photoUrl = null;
      return {};
    },
    // Анкета — последняя записанная: перечитывают её и после своей записи.
    'profile.get': () => ({ cv_meta: meta, profile: saved.at(-1) ?? null, photo_url: photoUrl }),
  };
  render(ProfileCv, {
    props: {
      ask: async (method, payload) => {
        asked.push([method, payload]);
        return (answers[method] ?? (() => ({})))();
      },
    },
  });
  return asked;
}

const PICKED = 'data:image/png;base64,AAAA';
const CROPPED = 'data:image/jpeg;base64,BBBB';

/** Снимок в окне обрезки «загрузился»: в jsdom картинки не грузятся сами. */
function loaded(image, width, height) {
  Object.defineProperty(image, 'naturalWidth', { value: width });
  Object.defineProperty(image, 'naturalHeight', { value: height });
  image.dispatchEvent(new Event('load'));
}

const methods = (asked) => asked.map(([method]) => method);

function typeInto(field, text) {
  field.value = text;
  field.dispatchEvent(new Event('input', { bubbles: true }));
  field.dispatchEvent(new Event('blur'));
}

describe('поле личных предпочтений', () => {
  it('растёт не выше десяти строк, а образование — без предела', async () => {
    // Раскладки в jsdom нет, и высоту не измерить: проверяется, что поле
    // объявило предел, по которому его подгоняет `fitHeight`.
    sheet({ name: 'cv.pdf', size: 2048, exists: true });

    const wishes = await vi.waitFor(() => screen.getByPlaceholderText('Дополнительные инструкции и ограничения для поиска'));
    const education = screen.getByPlaceholderText('Образование');

    expect(wishes.dataset.lines).toBe('10');
    expect(education.dataset.lines).toBeUndefined();
  });

  it('«О себе» схлопывается до тех же десяти строк', async () => {
    sheet(null);

    const about = await vi.waitFor(() => screen.getByPlaceholderText('О себе'));

    expect(about.dataset.lines).toBe('10');
  });
});

describe('новые поля анкеты', () => {
  it('набранное уезжает на мост записью анкеты', async () => {
    sheet(null);
    await vi.waitFor(() => screen.getByPlaceholderText('Отчество'));

    typeInto(screen.getByPlaceholderText('Отчество'), 'Сергеевич');
    typeInto(screen.getByPlaceholderText('Гражданство'), 'Россия');
    typeInto(screen.getByPlaceholderText(/Ссылка на резюме/), 'https://hh.ru/resume/1');
    await settled();

    expect(saved.at(-1)).toMatchObject({
      patronymic: 'Сергеевич',
      citizenship: 'Россия',
      resume_url: 'https://hh.ru/resume/1',
    });
  });

  it('дату набирают цифрами подряд, точки встают сами, уходит ISO', async () => {
    sheet(null);
    const born = await vi.waitFor(() => screen.getByPlaceholderText('дд.мм.гггг'));

    born.value = '15031990';
    born.dispatchEvent(new Event('input', { bubbles: true }));
    await settled();

    expect(born.value).toBe('15.03.1990');
    expect(saved.at(-1).birth_date).toBe('1990-03-15');
  });
});

describe('фото', () => {
  it('показывается по адресу, который дал мост', async () => {
    sheet(null, '/media/profile/photo.jpg');

    const photo = await vi.waitFor(() => screen.getByAltText('Фото'));

    expect(photo.getAttribute('src')).toBe('/media/profile/photo.jpg');
  });

  it('снимок обрезается в пропорции рамки, и мосту уходит вырезанное', async () => {
    // Раскладки в jsdom нет: размер рамки задаётся руками — 3 к 4.
    const drawn = [];
    HTMLCanvasElement.prototype.getContext = () => ({ drawImage: (...args) => drawn.push(args) });
    HTMLCanvasElement.prototype.toDataURL = () => CROPPED;
    const asked = sheet(null);
    const pick = await vi.waitFor(() => screen.getByTitle('Выбрать фото'));
    Object.defineProperty(pick.parentElement, 'offsetWidth', { value: 150 });
    Object.defineProperty(pick.parentElement, 'offsetHeight', { value: 200 });
    pick.click();
    await settled();

    loaded(screen.getByAltText('Снимок для обрезки'), 300, 1000);
    await settled();
    screen.getByRole('button', { name: 'Сохранить' }).click();
    await settled();

    // Высокий снимок 300×1000 под рамку 3:4 — середина во всю ширину.
    expect(drawn[0].slice(1)).toEqual([0, 300, 300, 400, 0, 0, 300, 400]);
    expect(asked).toContainEqual(['profile.store_photo', CROPPED]);
    expect(screen.queryByAltText('Снимок для обрезки')).toBeNull();
  });

  it('отменённая обрезка ничего не записывает', async () => {
    const asked = sheet(null);
    (await vi.waitFor(() => screen.getByTitle('Выбрать фото'))).click();
    await settled();

    screen.getByRole('button', { name: 'Отмена' }).click();
    await settled();

    expect(methods(asked)).not.toContain('profile.store_photo');
    expect(screen.queryByAltText('Снимок для обрезки')).toBeNull();
  });

  it('крестик убирает фото, и рамка пустеет', async () => {
    const asked = sheet(null, '/media/profile/photo.jpg');
    await vi.waitFor(() => screen.getByAltText('Фото'));

    screen.getByTitle('Убрать фото').click();
    await settled();

    expect(methods(asked)).toContain('profile.clear_photo');
    expect(screen.queryByAltText('Фото')).toBeNull();
  });
});

describe('файл резюме в анкете', () => {
  it('пропавший с диска не открывается', async () => {
    sheet({ name: 'cv.pdf', size: 2048, exists: false });

    const open = await vi.waitFor(() => screen.getByRole('button', { name: 'Открыть' }));

    expect(open.disabled).toBe(true);
  });

  it('лежащий на диске открывается', async () => {
    sheet({ name: 'cv.pdf', size: 2048, exists: true });

    const open = await vi.waitFor(() => screen.getByRole('button', { name: 'Открыть' }));

    expect(open.disabled).toBe(false);
  });
});
