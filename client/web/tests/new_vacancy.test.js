// Следствия правил окна «Добавить вакансию»: заслон, запор и приём итога.

import { describe, expect, it } from 'vitest';

import { blankVacancy, pasteLock, settleHandMade, vacancyNamed } from '../state/new_vacancy.js';

describe('заслон формы заведения вакансии', () => {
  it('над пустой формой кнопка заперта', () => {
    // Мост такую всё равно отобьёт: строка без названия в списке выглядит
    // пустой. Открытая кнопка меняла бы карточку на плашку отказа.
    expect(vacancyNamed(blankVacancy())).toBe(false);
  });

  it('одного названия довольно', () => {
    // Остальное дописывают в карточке: ссылку и стек человек копирует не
    // всегда, а завести найденное надо в тот миг, когда увидел.
    expect(vacancyNamed({ ...blankVacancy(), title: 'Senior Python Developer' })).toBe(true);
  });

  it('пробелы названием не считаются', () => {
    // Пробельное название дошло бы до базы строкой, которую в списке не видно
    // и не найти поиском.
    expect(vacancyNamed({ ...blankVacancy(), title: '   ' })).toBe(false);
  });
});

describe('запор формы заведения вакансии', () => {
  const quiet = { running: false, lockedTip: '' };

  it('во время обхода текст не заводится: его разбирает конвейер на месте прогона', () => {
    expect(pasteLock({ mode: 'text' }, false, { ...quiet, running: true })).toBe('Идёт обход');
  });

  it('без живых систем текст не заводится, и слова — те же, что у кнопок бота', () => {
    expect(pasteLock({ mode: 'text' }, false, { ...quiet, lockedTip: 'Нет модели' })).toBe('Нет модели');
  });

  it('обход старше погасшей лампы: он кончится сам', () => {
    expect(pasteLock({ mode: 'text' }, false, { running: true, lockedTip: 'Нет модели' }))
      .toBe('Идёт обход');
  });

  it('поля без отклика обходу и лампам не мешают: ложатся в базу мимо бота', () => {
    expect(pasteLock({ mode: 'fields' }, false, { running: true, lockedTip: 'Нет модели' })).toBe('');
  });

  it('поля с откликом заперты обходом: передача идёт через место прогона', () => {
    expect(pasteLock({ mode: 'fields' }, true, { ...quiet, running: true })).toBe('Идёт обход');
    expect(pasteLock({ mode: 'fields' }, true, quiet)).toBe('');
  });

  it('текст свободен, когда всё живо и обхода нет', () => {
    expect(pasteLock({ mode: 'text' }, false, quiet)).toBe('');
  });
});

describe('итог ручного заведения', () => {
  /** Черновик, ушедший боту, — каким его держит оболочка. */
  const handedDraft = () => ({ draft: { ...blankVacancy(), raw_text: 'Ищем повара' }, handed: true });

  it('заведено — черновик сброшен, окно никуда не переходит', () => {
    const held = handedDraft();

    expect(settleHandMade(held, { outcome: 'ok', vacancy_id: 6 })).toBe(null);
    expect(held.draft).toEqual(blankVacancy());
  });

  it('повтор — черновик сброшен, переход на существующую', () => {
    const held = handedDraft();

    expect(settleHandMade(held, { outcome: 'duplicate', vacancy_id: 5 })).toBe(5);
    expect(held.draft).toEqual(blankVacancy());
  });

  it('неудача — черновик цел и по-прежнему не стирается закрытием окна', () => {
    // Отказ места прогона приходит вестью раньше ответа на зов, и окно
    // закрывается уже после него: сними оболочка тут отметку «отдано боту», и
    // закрытие стёрло бы набранное.
    for (const outcome of ['llm', 'embed', 'article', undefined]) {
      const held = handedDraft();

      expect(settleHandMade(held, { outcome, vacancy_id: null })).toBe(null);
      expect([held.draft.raw_text, held.handed]).toEqual(['Ищем повара', true]);
    }
  });
});
