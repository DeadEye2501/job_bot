// Контакты вакансии: куда ведёт нажатие на контакт.

import { describe, expect, it } from 'vitest';

import { contactHref } from '../state/vacancy_contacts.js';

describe('переход по контакту вакансии', () => {
  it('ссылка со схемой открывается как есть', () => {
    expect(contactHref('https://example.test/vacancy/1?from=list')).toBe('https://example.test/vacancy/1?from=list');
  });

  it('ссылка без схемы открывается по https', () => {
    // Разбор кладёт ссылку так, как она написана в объявлении, а там её часто
    // пишут без схемы.
    expect(contactHref('example.test/jobs/1')).toBe('https://example.test/jobs/1');
  });

  it('ссылка с портом остаётся ссылкой: порт не схема', () => {
    expect(contactHref('example.test:8080/jobs')).toBe('https://example.test:8080/jobs');
  });

  it('ссылка Telegram и готовые письмо и звонок открываются как есть', () => {
    expect(contactHref('tg://resolve?domain=example')).toBe('tg://resolve?domain=example');
    expect(contactHref('mailto:hr@example.test')).toBe('mailto:hr@example.test');
    expect(contactHref('tel:+79001234567')).toBe('tel:+79001234567');
  });

  it('чужая схема наружу не уходит', () => {
    // Контакт вынут из чужого объявления: `javascript:` и `file:` открывать
    // нельзя, и адрес переписывается на обычный.
    expect(contactHref('javascript:alert(1)')).toBe('https://alert(1)');
  });

  it('почта открывается письмом', () => {
    expect(contactHref('HR@Example.test')).toBe('mailto:HR@Example.test');
  });

  it('телефон набирается номером без пробелов и скобок', () => {
    expect(contactHref('+7 (900) 123-45-67')).toBe('tel:+79001234567');
  });
});
