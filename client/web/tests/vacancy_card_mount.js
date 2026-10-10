// Карточка вакансии, смонтированная для живой проверки.
//
// Общая на все живые проверки карточки: набор свойств у них один, и разное у
// проверок только то, чем отвечает мост. Написанный в каждом файле заново,
// набор разошёлся бы на первом же новом свойстве карточки.

import { flushSync, mount, unmount } from 'svelte';

import VacancyCard from '../app/VacancyCard.svelte';
import { livingProps } from './live_props.svelte.js';

/** Смонтировать карточку вакансии №7 над мостом `answer(method, payload)`.
 *
 * Отдаёт, что спрашивали у моста и что сказано плашкой, узел карточки, смену
 * одного свойства — как её делает живой родитель — и разборку.
 */
export function mountVacancyCard(answer) {
  const asked = [];
  const said = [];
  const [props, change] = livingProps({
    ask: async (method, payload) => {
      asked.push([method, payload]);
      return answer(method, payload);
    },
    say: (text) => said.push(text),
    events: { on: () => () => {} },
    lockedTip: '',
    vacancyId: 7,
    oncontacts: () => {},
    onclose: () => {},
    onchanged: () => {},
  });
  const host = document.createElement('div');
  document.body.append(host);
  const mounted = mount(VacancyCard, { target: host, props });
  return {
    asked,
    said,
    host,
    change,
    remove: () => {
      flushSync(() => unmount(mounted));
      host.remove();
    },
  };
}

/** Раскрыть меню действий карточки. */
export function openActions(host) {
  host.querySelector('button[title="Действия"]').click();
  flushSync();
}

/** Нажать кнопку с такой подписью. Ищется по всей странице: окна карточки
 *  встают поверх неё, а не внутри. */
export function press(label) {
  const found = [...document.querySelectorAll('button')].find((one) =>
    one.textContent.includes(label),
  );
  found.click();
}
