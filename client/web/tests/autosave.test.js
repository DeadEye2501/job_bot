// Следствия отложенной записи: когда набранное уезжает на мост и когда молчит.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { autosave } from '../state/autosave.js';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function writer() {
  const sent = [];
  return { sent, save: (value) => sent.push(value) };
}

describe('отложенная запись', () => {
  it('набранное уезжает не сразу, а спустя паузу', () => {
    // Запись на каждый знак послала бы мосту по вопросу на букву.
    const { sent, save } = writer();
    const notes = autosave({ delay: 800, save });

    notes.typed('Позвонить');
    vi.advanceTimersByTime(700);
    expect(sent).toEqual([]);

    vi.advanceTimersByTime(100);
    expect(sent).toEqual(['Позвонить']);
  });

  it('набранное подряд уезжает один раз и целиком', () => {
    // Пауза считается от последнего знака: иначе на середине слова уехала бы
    // половина фразы, и в базе полежало бы недописанное.
    const { sent, save } = writer();
    const notes = autosave({ delay: 800, save });

    notes.typed('Поз');
    vi.advanceTimersByTime(500);
    notes.typed('Позвонить');
    vi.advanceTimersByTime(800);

    expect(sent).toEqual(['Позвонить']);
  });

  it('уход из поля отправляет немедленно и гасит отложенное', () => {
    // Человек ушёл на другую вакансию — ждать паузы уже нечего, а отложенное
    // выстрелило бы вторым тем же вопросом.
    const { sent, save } = writer();
    const notes = autosave({ delay: 800, save });

    notes.typed('Позвонить');
    notes.flush();
    expect(sent).toEqual(['Позвонить']);

    vi.advanceTimersByTime(2000);
    expect(sent).toEqual(['Позвонить']);
  });

  it('лежащее в базе второй раз не уезжает', () => {
    // Иначе уход из нетронутого поля писал бы в базу то же самое, а карточка
    // перечитывалась бы на каждый взгляд.
    const { sent, save } = writer();
    const notes = autosave({ delay: 800, save });

    notes.known('Позвонить');
    notes.typed('Позвонить');
    notes.flush();

    expect(sent).toEqual([]);
  });

  it('одни пробелы поверх пустоты записью не считаются', () => {
    // Мост сводит пробельную заметку к пустой и отвечает пустотой: не сравняй
    // мы их здесь, каждая пауза слала бы вопрос заново, без конца.
    const { sent, save } = writer();
    const notes = autosave({ delay: 800, save });

    notes.known('');
    notes.typed('   ');
    notes.flush();

    expect(sent).toEqual([]);
  });

  it('записанное однажды уезжает снова, если его поправили', () => {
    const { sent, save } = writer();
    const notes = autosave({ delay: 800, save });

    notes.typed('Позвонить');
    notes.flush();
    notes.typed('Позвонить в среду');
    notes.flush();

    expect(sent).toEqual(['Позвонить', 'Позвонить в среду']);
  });
});
