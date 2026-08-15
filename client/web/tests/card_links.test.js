// Следствия связей карточки: куда ведут имя HR и имя компании.

import { describe, expect, it } from 'vitest';

import { cardLinks } from '../state/card_links.js';

const CARD = {
  hr: { id: 4, name: 'Иван' },
  company_id: 7,
  company_name: 'Ромашка',
};

describe('переходы из карточки', () => {
  it('имя HR ведёт в его карточку контактов', () => {
    expect(cardLinks(CARD).hrCard).toEqual({ tab: 'people', id: 4 });
  });

  it('непривязанного HR открывать негде', () => {
    expect(cardLinks({ ...CARD, hr: null }).hrCard).toBe(null);
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
});
