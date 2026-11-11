// @vitest-environment jsdom
//
// Живая карточка вакансии над подставным мостом.
//
// Панель одна на весь список: выбор другой строки не заводит компонент заново,
// а меняет ему одно свойство. Не назови эффект этот номер своей зависимостью —
// на экране осталась бы прежняя вакансия, и человек правил бы статус не той.

import { afterEach, describe, expect, it } from 'vitest';

import { press } from './press.js';
import { settled } from './settled.js';
import { mountVacancyCard, openActions } from './vacancy_card_mount.js';
import { vacancyDetail } from './vacancy_detail.js';

let card = null;

afterEach(() => {
  card?.remove();
  card = null;
});

/** Кнопка контакта вакансии по его значению. */
function contactButton(value) {
  return [...card.host.querySelectorAll('.vac-contact > button')].find((one) => one.textContent.trim() === value);
}

/** Прогнать проверку с подменённым буфером обмена; `run` получает список
 *  положенного в буфер.
 *
 * Буфер подменён на одну проверку: оставленный подменённым, он отвечал бы и
 * соседним файлам, что пойдут в том же окружении.
 */
async function withClipboard(run) {
  const own = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
  const copied = [];
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: async (text) => copied.push(text) },
    configurable: true,
  });
  try {
    await run(copied);
  } finally {
    if (own) Object.defineProperty(navigator, 'clipboard', own);
    else delete navigator.clipboard;
  }
}

function screen(extra = {}) {
  card = mountVacancyCard((method, payload) => ({ vacancy: vacancyDetail(payload, extra) }));
  return { asked: card.asked, change: card.change, text: () => card.host.textContent };
}

describe('живая карточка вакансии', () => {
  it('перечитывается, когда открыли другую вакансию', async () => {
    const { asked, change, text } = screen();
    await settled();
    expect(asked).toEqual([{ method: 'vacancies.detail', payload: 7 }]);

    change('vacancyId', 8);
    await settled();

    expect(asked).toEqual([
      { method: 'vacancies.detail', payload: 7 },
      { method: 'vacancies.detail', payload: 8 },
    ]);
    expect(text()).toContain('Вакансия 8');
  });

  it('зарплату показывает пилюлей из разобранных чисел, а не строкой поста', async () => {
    // Наставление разбора велит модели брать зарплату дословно, и в поле
    // ложится написанное автором: «🎯 ЗП: действительно готовы обсудить ваши
    // пожелания». В пилюле такому не место — она показывает только числа.
    const { text } = screen({
      salary: '🎯 ЗП: действительно готовы обсудить ваши пожелания',
      salary_min: 500000,
      salary_max: 700000,
      salary_currency: '֏',
    });

    await settled();

    expect(text()).toContain('от 500000 до 700000 ֏');
    expect(text()).not.toContain('готовы обсудить');
  });

  it('нажатие на название кладёт его в буфер обмена и говорит об этом', async () => {
    await withClipboard(async (copied) => {
      screen({ title: 'Повар в бистро' });
      await settled();

      card.host.querySelector('.det-title').click();
      await settled();

      expect(copied).toEqual(['Повар в бистро']);
      expect(card.said).toContain('Название скопировано');
    });
  });

  it('нажатие на почту в контактах кладёт её в буфер, а не открывает письмом', async () => {
    // Письмо открывает почтовая программа системы, а её может не быть: адрес
    // нужен человеку текстом, вставить в свою почту.
    await withClipboard(async (copied) => {
      const { asked } = screen({ contacts: [{ id: 1, value: 'hr@example.test' }] });
      await settled();

      contactButton('hr@example.test').click();
      await settled();

      expect(copied).toEqual(['hr@example.test']);
      expect(card.said).toContain('Почта скопирована');
      expect(asked.some((one) => one.method === 'system.open_url')).toBe(false);
    });
  });

  it('почта в контактах не подсвечивается ссылкой, прочие контакты — да', async () => {
    screen({ contacts: [{ id: 1, value: 'hr@example.test' }, { id: 2, value: 'example.test/jobs' }] });
    await settled();

    expect(contactButton('hr@example.test').classList).not.toContain('link-hover');
    expect(contactButton('example.test/jobs').classList).toContain('link-hover');
  });

  it('удаление вакансии уходит на мост только после подтверждения', async () => {
    // Удаление необратимо: пункт меню лишь спрашивает, а удаляет кнопка окна.
    screen();
    await settled();

    openActions(card.host);
    press('Удалить');
    await settled();
    const deleted = () => card.asked.filter((one) => one.method === 'vacancies.delete');
    expect(deleted()).toEqual([]);

    [...document.querySelectorAll('.modal-actions button')].at(-1).click();
    await settled();

    expect(deleted()).toHaveLength(1);
  });
});

