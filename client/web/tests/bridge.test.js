// Следствия обёртки моста: что экран получает, позвав питона.
//
// Предмет — дорога ответа, а не то, что по ней едет. Мост подделан целиком:
// настоящий живёт в окне, а окна у прогона нет, и подделка садится туда же,
// куда сядет он, — в `window.pywebview.api`.

import { afterEach, describe, expect, it } from 'vitest';

import { Refused, call, ready } from '../api/bridge.js';

function bridgeAnswers(answers) {
  const asked = [];
  globalThis.window = {
    pywebview: {
      api: {
        system: {
          health: async (...args) => {
            asked.push(args);
            const next = answers.shift();
            if (next instanceof Error) throw next;
            return next;
          },
        },
      },
    },
    addEventListener: () => {},
  };
  return asked;
}

afterEach(() => {
  delete globalThis.window;
});

describe('ответ моста', () => {
  it('успех отдаёт нагрузку, а не конверт', async () => {
    // Конверт — договор двоих, и экрану он не нужен: разворачивай его каждый
    // экран сам, забытое `.ok` читалось бы как «поле пропало».
    bridgeAnswers([{ ok: { db: true } }]);

    expect(await call('system.health')).toEqual({ db: true });
  });

  it('отказ поднимает отказ, а не возвращает его значением', async () => {
    // Возвращённый отказ экран обязан проверять после каждого зова, и первый
    // же забытый разбор показал бы человеку пустой список вместо объяснения.
    bridgeAnswers([{ fail: 'denied', detail: 'Резюме не выбрано.' }]);

    await expect(call('system.health')).rejects.toBeInstanceOf(Refused);
  });

  it('поля отказа доезжают вместе с ним', async () => {
    // По ним экран откатывает отметку у нужной строки: без номера вакансии он
    // не знает, какую именно строку красить обратно.
    bridgeAnswers([
      { fail: 'denied', detail: 'Нельзя', vacancy_id: 17, action: 'delete' },
    ]);

    const refusal = await call('system.health').catch((e) => e);

    expect(refusal.fields).toEqual({ vacancy_id: 17, action: 'delete' });
    expect(refusal.kind).toBe('denied');
    expect(refusal.message).toBe('Нельзя');
  });

  it('успех со значением «ложь» остаётся успехом', async () => {
    // Пустой перечень, ноль и «нет» — обычные ответы: столько-то непрочитанных,
    // столько-то строк. Проверяй мы истинность вместо предметности, каждый
    // такой ответ приезжал бы экрану поломкой.
    bridgeAnswers([{ ok: false }]);

    expect(await call('system.health')).toBe(false);
  });

  it('не-объект в ответе становится отказом, а не поломкой разбора', async () => {
    // Мост, ответивший строкой или числом, сломан. Разбор такого ответа сам
    // бросил бы `TypeError` мимо конверта, и экран показал бы трассировку
    // вместо плашки.
    bridgeAnswers(['я не конверт']);

    await expect(call('system.health')).rejects.toBeInstanceOf(Refused);
  });

  it('незнакомое имя метода — отказ, а не падение на месте зова', async () => {
    // Мост и страница расходятся именами при переименовании на любой из сторон.
    // Упади зов на `undefined is not a function`, экран увидел бы поломку без
    // намёка на то, чьё имя разошлось.
    bridgeAnswers([]);

    const refusal = await call('vacancies.нетТакого').catch((e) => e);

    expect(refusal).toBeInstanceOf(Refused);
    expect(refusal.fields.path).toBe('vacancies.нетТакого');
  });

  it('молчание моста тоже отказ, а не успех с пустотой', async () => {
    // Метод, вернувший ничего, — это поломка канала, а не ответ. Прими её
    // экран за успех, он нарисовал бы пустой экран вместо плашки беды.
    bridgeAnswers([undefined]);

    await expect(call('system.health')).rejects.toBeInstanceOf(Refused);
  });
});

describe('готовность', () => {
  it('поднятый мост не заставляет себя ждать', async () => {
    // Страница грузится дольше моста, и к первому зову он обычно уже на месте.
    // Ожидание события, которое уже случилось, повисло бы навсегда.
    bridgeAnswers([]);

    await expect(ready()).resolves.toBeUndefined();
  });
});
