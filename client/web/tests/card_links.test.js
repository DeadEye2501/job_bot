// Следствия связей карточки: куда ведут имя HR, его ник, компания и её сайт.

import { describe, expect, it } from 'vitest';

import { cardLinks } from '../state/card_links.js';

const CARD = {
  hr: { id: 4, name: 'Иван', telegram_username: 'ivanov' },
  company_id: 7,
  company_name: 'Ромашка',
  company_website: 'romashka.ru',
};

describe('переходы из карточки', () => {
  it('ник HR ведёт в Telegram', () => {
    // Без перехода карточка — тупик: до переписки надо идти через контакты и
    // искать человека руками.
    expect(cardLinks(CARD).hrChat).toBe('https://t.me/ivanov');
  });

  it('HR без ника в Telegram не ведёт', () => {
    const hr = { id: 4, name: 'Иван', telegram_username: '' };
    expect(cardLinks({ ...CARD, hr }).hrChat).toBe(null);
  });

  it('имя HR ведёт в его карточку контактов', () => {
    expect(cardLinks(CARD).hrCard).toEqual({ tab: 'people', id: 4 });
  });

  it('непривязанного HR открывать негде', () => {
    expect(cardLinks({ ...CARD, hr: null })).toMatchObject({ hrChat: null, hrCard: null });
  });

  it('привязанная компания ведёт в свою карточку контактов', () => {
    expect(cardLinks(CARD).companyCard).toEqual({ tab: 'companies', id: 7 });
  });

  it('разобранная из текста компания ведёт в подборщик со своим именем', () => {
    // Имя есть, а связи нет: человек нажимает на него и сразу видит
    // совпадения, вместо того чтобы набирать то же слово в поиске подборщика.
    const links = cardLinks({ ...CARD, company_id: null });
    expect(links.companyCard).toBe(null);
    expect(links.companyPick).toBe('Ромашка');
  });

  it('привязанную компанию подборщиком не переспрашивают', () => {
    expect(cardLinks(CARD).companyPick).toBe(null);
  });

  it('сайт компании ведёт наружу', () => {
    expect(cardLinks(CARD).site).toBe('https://romashka.ru');
  });

  it('без сайта перехода нет', () => {
    expect(cardLinks({ ...CARD, company_website: null }).site).toBe(null);
  });
});
