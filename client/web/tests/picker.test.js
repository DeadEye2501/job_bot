// Следствия окна выбора: когда выбранным можно связывать.

import { describe, expect, it } from 'vitest';

import { companyTitle } from '../state/companies.js';
import { personName } from '../state/people.js';
import { candidate, labels, linkReady, sameName } from '../state/picker.js';

describe('запор кнопки «Связать»', () => {
  it('пока никого не выбрали, связывать нечем', () => {
    expect(linkReady({ current: 4, chosen: null })).toBe(false);
  });

  it('выбор того же, кто уже привязан, кнопку не отпирает', () => {
    // Иначе нажатие переписывает привязку тем же значением и пишет в журнал
    // перемену, которой не было.
    expect(linkReady({ current: 4, chosen: 4 })).toBe(false);
  });

  it('выбор другого отпирает кнопку', () => {
    expect(linkReady({ current: 4, chosen: 9 })).toBe(true);
  });

  it('выбор при пустой привязке отпирает кнопку', () => {
    expect(linkReady({ current: null, chosen: 9 })).toBe(true);
  });
});

describe('строка окна выбора', () => {
  it('подпись берётся готовым правилом предмета', () => {
    // Один и тот же человек, названный в списке и в подборщике по-разному,
    // читается как двое разных.
    expect(
      candidate({
        id: 4,
        icon: 'person',
        avatar: 'data:image/png;base64,x',
        line: { name: 'Ирина', sub: '@irina_hr · Ромашка' },
        count: 3,
        blocked: false,
      }),
    ).toEqual({
      id: 4,
      icon: 'person',
      avatar: 'data:image/png;base64,x',
      name: 'Ирина',
      sub: '@irina_hr · Ромашка',
      count: 3,
      blocked: false,
    });
  });

  it('снимка может не быть — на его месте встанет значок', () => {
    // У компании снимка нет вовсе, но поле остаётся: строка выбора одна на оба
    // предмета, и разбирать в ней два набора полей значило бы держать две.
    expect(
      candidate({
        id: 7,
        icon: 'domain',
        line: { name: 'Ромашка', sub: 'romashka.ru' },
        count: 0,
        blocked: true,
      }).avatar,
    ).toBe(null);
  });
});

describe('набранное имя против заведённых карточек', () => {
  const ROWS = [{ id: 1, name: 'Nitka' }, { id: 2, name: 'Playrix' }];
  const PEOPLE = [
    { id: 1, name: 'Ирина', telegram_username: 'irina_hr' },
    { id: 2, name: 'Ирина', telegram_username: 'ira_recr' },
    { id: 3, name: 'Олег' },
    { id: 4, name: null, telegram_username: 'anna_hr' },
    { id: 5, name: null, telegram_username: null },
  ];
  const CO = (row) => companyTitle(row).name;

  it('подсказке уезжают подписи, а не номера', () => {
    // Номер карточки человеку не о чем сравнивать с тем, что он набрал.
    expect(labels(ROWS, CO)).toEqual(['Nitka', 'Playrix']);
  });

  it('тёзок в подписи различает ник', () => {
    // Имя человека уникальным не бывает: две «Ирины» без ника — две
    // одинаковые строки, и выбрать из них нужную нечем.
    expect(labels(PEOPLE, personName).slice(0, 2)).toEqual([
      'Ирина · @irina_hr',
      'Ирина · @ira_recr',
    ]);
  });

  it('без ника подпись остаётся одним именем', () => {
    // Разделитель в конце читался бы как потерянное слово.
    expect(labels(PEOPLE, personName)[2]).toBe('Олег');
  });

  it('выбранную подпись узнают целиком', () => {
    expect(sameName(PEOPLE, 'Ирина · @ira_recr', personName).id).toBe(2);
  });

  it('набранное одно имя узнают тоже', () => {
    // Человек набирает имя, а не подпись: не узнай форма его, она завела бы
    // вторую карточку поверх уже заведённой.
    expect(sameName(PEOPLE, 'олег', personName).id).toBe(3);
  });

  it('набранное строчными узнаёт ту же карточку', () => {
    // «nitka» и «Nitka» — одна компания: не узнай её форма, человек завёл бы
    // вторую такую же вместо того, чтобы выбрать эту.
    expect(sameName(ROWS, ' nitka ', CO)).toEqual({ id: 1, name: 'Nitka' });
  });

  it('незнакомое имя не выдают за чужую карточку', () => {
    // Пустота здесь значит «такой ещё нет» — по ней форма и заводит новую.
    expect(sameName(ROWS, 'WorldQuant', CO)).toBe(null);
  });

  it('безымянного зовут ником, а не словом «null»', () => {
    // `HR.name` бывает пустым: бот заводит человека из поста, где был только
    // ник. Собранная здесь подпись печатала бы «null · @anna_hr».
    expect(labels(PEOPLE, personName)[3]).toBe('@anna_hr');
  });

  it('человека без имени и без ника зовут номером, а не пустотой', () => {
    // Пустая строка в подсказке роняет просеивание на первом же знаке.
    expect(labels(PEOPLE, personName)[4]).toBe('Человек #5');
  });

  it('пустое имя не выдают за совпадение', () => {
    // Иначе первый безымянный отвечал бы на любое пустое сравнение.
    expect(sameName(PEOPLE, '', personName)).toBe(null);
  });
});
