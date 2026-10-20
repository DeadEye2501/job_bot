// Окна заведения по адресу: чем закрыто пустое и что сказано по удаче.

import { describe, expect, it } from 'vitest';

import { NEW_CARD } from '$state/new_card.js';

describe('окна заведения по адресу', () => {
  it('пустое и пробелы не заводятся ни каналом, ни сайтом, ни контактом', () => {
    for (const form of [NEW_CARD.channel, NEW_CARD.aggregator, NEW_CARD.contact]) {
      expect(form.named(form.blank())).toBe(false);
      expect(form.named('   ')).toBe(false);
      expect(form.named('x')).toBe(true);
    }
  });

  it('канал назван ником из ответа: заведён он сейчас или был раньше', () => {
    expect(NEW_CARD.channel.done('', { created: true, username: 'jobs' })).toBe('Канал добавлен: @jobs');
    expect(NEW_CARD.channel.done('', { created: false, username: 'jobs' }))
      .toBe('Канал @jobs уже был заведён');
  });

  it('агрегатор назван сайтом из ответа: набранный адрес мост приводит к хосту', () => {
    const answer = (status) => ({ status, aggregator: { host: 'example.test' } });
    expect(NEW_CARD.aggregator.done('https://www.Example.test/', answer('created')))
      .toBe('Агрегатор добавлен: example.test');
    expect(NEW_CARD.aggregator.done('', answer('exists'))).toBe('example.test уже был заведён');
  });

  it('вакансия по полям: повтор говорит словами моста, а не «заведена»', () => {
    const fields = { mode: 'fields' };
    expect(NEW_CARD.vacancy.done(fields, { created: true })).toBe('Вакансия заведена');
    expect(NEW_CARD.vacancy.done(fields, { created: false, message: 'Такая вакансия уже существует' }))
      .toBe('Такая вакансия уже существует');
  });
});
