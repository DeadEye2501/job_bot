// Следствия списка компаний: чем подписана строка.

import { describe, expect, it } from 'vitest';

import { companyCandidate, companyLine, companyNamed, siteHref } from '../state/companies.js';

describe('подпись компании в списке', () => {
  it('под именем стоят сайт и алиасы', () => {
    // Компанию узнают по имени, а различают по домену: две «Ромашки» с
    // разными сайтами — разные компании, и без второй строки они неотличимы.
    expect(companyLine({ id: 1, name: 'Ромашка', website: 'romashka.ru', aliases: ['ООО Ромашка'] }))
      .toEqual({ name: 'Ромашка', sub: 'romashka.ru · алиасы: ООО Ромашка' });
  });

  it('без сайта показывают одни алиасы', () => {
    // Заведённой руками компании домен знают не всегда, а алиасы у неё
    // есть — по ним её и сводят с той, что пришла из объявления.
    expect(companyLine({ id: 3, name: 'Ромашка', website: '', aliases: ['ООО Ромашка'] }))
      .toEqual({ name: 'Ромашка', sub: 'алиасы: ООО Ромашка' });
  });

  it('без сайта и алиасов так и сказано', () => {
    // Пустая строка читалась бы как недогрузившаяся: человек ждал бы, что
    // сайт вот-вот появится.
    expect(companyLine({ id: 2, name: 'Ромашка', website: '', aliases: [] }))
      .toEqual({ name: 'Ромашка', sub: 'без сайта' });
  });

  it('безымянная компания названа номером', () => {
    // Имя приходит из объявления и бывает пустым. Показать нечего, но строка
    // должна остаться нажимаемой — иначе до карточки не добраться.
    expect(companyLine({ id: 7, name: '', website: 'x.ru', aliases: [] }))
      .toEqual({ name: 'Компания #7', sub: 'x.ru' });
  });
});

describe('переход на сайт компании', () => {
  it('домен без схемы дополняется до https', () => {
    // В базе лежит то, что модель вынула из чужого поста, — чаще всего голый
    // домен, и без схемы система открыла бы его как файл рядом со страницей.
    expect(siteHref('romashka.ru')).toBe('https://romashka.ru');
  });

  it('адрес со схемой берётся как есть', () => {
    expect(siteHref('http://romashka.ru')).toBe('http://romashka.ru');
  });

  it('чужая схема наружу не уходит', () => {
    // Строка пришла из чужого объявления: `javascript:` и `file:` открывать
    // нельзя вовсе, и вместо отказа адрес переписывается на обычный.
    expect(siteHref('javascript:alert(1)')).toBe('https://alert(1)');
  });

  it('домен с портом остаётся доменом', () => {
    // Двоеточие после точки — это порт, а не схема: приняв его за схему, мы
    // отправили бы человека на «https://8080».
    expect(siteHref('example.com:8080')).toBe('https://example.com:8080');
  });

  it('пустое поле ссылки не даёт', () => {
    // Иначе на карточке висит мёртвая ссылка в никуда.
    expect(siteHref('')).toBe(null);
  });
});

describe('строка компании в окне выбора', () => {
  const COMPANY = {
    id: 7,
    name: 'Ромашка',
    website: 'romashka.ru',
    aliases: ['ООО Ромашка'],
    vacancy_count: 5,
    is_blacklisted: false,
  };

  it('называет компанию тем же, чем и список контактов', () => {
    expect(companyCandidate(COMPANY)).toEqual({
      id: 7,
      icon: 'domain',
      avatar: null,
      name: 'Ромашка',
      sub: 'romashka.ru · алиасы: ООО Ромашка',
      count: 5,
      blocked: false,
    });
  });

  it('отсеянная помечена отдельно', () => {
    expect(companyCandidate({ ...COMPANY, is_blacklisted: true }).blocked).toBe(true);
  });
});

describe('чем компания названа при заведении', () => {
  const DRAFT = { name: '', website: '', aliases: '', notes: '' };

  it('названия довольно', () => {
    expect(companyNamed({ ...DRAFT, name: 'Ромашка' })).toBe(true);
  });

  it('без названия заводить нечего', () => {
    expect(companyNamed({ ...DRAFT, name: '   ' })).toBe(false);
  });

  it('одного сайта названием не считают', () => {
    // Домен приезжает из объявления и есть у многих: без имени компанию по нему
    // не узнать в списке, а строка выбора осталась бы безымянной.
    expect(companyNamed({ ...DRAFT, website: 'romashka.ru' })).toBe(false);
  });
});
