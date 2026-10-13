// @vitest-environment jsdom
//
// Следствия живого поля заметки: куда уезжает набранное, когда поле закрывают.
//
// Проверки договора по разметке (`notes_field.test.js`) сторожат, что номер
// записи передан доводом и что поле заводится заново на каждую запись. Само
// следствие — прощальная отправка после смены записи — видно только здесь: она
// случается в миг закрытия поля, и другого способа её увидеть нет.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import NotesField from '../components/NotesField.svelte';
import { typed } from './press.js';

afterEach(cleanup);

/** Поле заметки с записанными за ним отправками. */
function notes(owner) {
  const sent = [];
  const shown = render(NotesField, {
    props: {
      value: '',
      placeholder: 'Заметки…',
      // Пауза длинная нарочно: набранное не должно уехать само по себе,
      // предмет здесь — только прощальная отправка.
      delay: 60_000,
      owner,
      save: async (id, text) => {
        sent.push({ id, text });
        return text;
      },
    },
  });
  return { sent, shown, box: shown.getByPlaceholderText('Заметки…') };
}


describe('живое поле заметки', () => {
  it('на прощание досылает набранное к той записи, у которой набирали', async () => {
    // Человек закрывает карточку, не дождавшись паузы: набранное не должно
    // пропасть вместе с полем. А прощание случается уже после того, как
    // карточка сменила запись — читай поле номер в этот миг, набранное уехало
    // бы к соседней и затёрло её заметку, а прежняя осталась бы ни с чем.
    const { sent, shown, box } = notes(7);

    typed(box, 'позвонить в пятницу');
    // Подпись меняется вместе с номером и наблюдается тут же: без неё проверка
    // не отличала бы «запись сменилась» от «смена не доехала» и была бы зелена
    // в том числе на поле, читающем номер в миг отправки.
    await shown.rerender({ owner: 8, placeholder: 'Заметки о компании…' });
    expect(shown.getByPlaceholderText('Заметки о компании…')).toBe(box);

    shown.unmount();

    expect(sent).toEqual([{ id: 7, text: 'позвонить в пятницу' }]);
  });
});
