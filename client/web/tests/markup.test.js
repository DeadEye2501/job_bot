// Следствия ходока по разметке: на чём он держится и на чём сдаётся.
//
// На нём стоят оба сторожа договоров компонентов, и молчаливая ошибка здесь
// гасит их разом: не найдя постановок, они проходят зелёными по пустому
// списку.

import { describe, expect, it } from 'vitest';

import { placementsIn } from './markup.js';

describe('ходок по разметке', () => {
  it('берёт сам тег, а не всё до конца файла', () => {
    const text = '<div>\n  <NotesField owner={7} />\n</div>\n<p>хвост</p>\n';

    const [one] = placementsIn(text, '<NotesField');

    expect(one.tag).toBe('<NotesField owner={7} ');
    expect(one.before).toBe('<div>\n  ');
  });

  it('находит все постановки, а не первую', () => {
    const text = '<X a={1} />\n<X a={2} />\n';

    expect(placementsIn(text, '<X').map((one) => one.tag)).toEqual([
      '<X a={1} ',
      '<X a={2} ',
    ]);
  });

  it('на теге с детьми говорит словами, а не уходит в круг', () => {
    const text = '<X a={1}>дети</X>\n';

    expect(() => placementsIn(text, '<X', 'Карточка.svelte')).toThrow(/Карточка\.svelte/);
  }, 2000);

  it('на теге с детьми не хватается за конец следующего тега', () => {
    // Настоящая разметка тегом с детьми не кончается, и закрывающие знаки
    // находились у постороннего тега ниже: две постановки склеивались в одну,
    // а всё между ними уходило из-под сторожа беззвучно.
    const text = '<X a={1}>дети</X>\n<Y b={2} />\n';

    expect(() => placementsIn(text, '<X', 'Карточка.svelte')).toThrow(/Карточка\.svelte/);
  });

  it('не путает тег с однофамильцем', () => {
    // Иначе договор поля сторожился бы на обёртке вокруг него, а само поле
    // проходило бы мимо проверки.
    const text = '<NotesFieldGroup a={1} />\n<NotesField b={2} />\n';

    expect(placementsIn(text, '<NotesField').map((one) => one.tag)).toEqual([
      '<NotesField b={2} ',
    ]);
  });

  it('не режет тег по стрелке в доводе', () => {
    const text = '<X onblock={() => run()} b={2} />\n';

    expect(placementsIn(text, '<X')[0].tag).toBe('<X onblock={() => run()} b={2} ');
  });
});
