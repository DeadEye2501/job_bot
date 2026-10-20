// Память разделов: что окно помнит о каждом разделе, пока открыто, — вкладку,
// открытую карточку и выбранные человеком отбор и порядок списка вакансий.
//
// Держит её оболочка, а не экраны: экран снимается при уходе из раздела, и
// вернувшись, человек попадал бы на первую вкладку без карточки, а не туда, где
// был. Карточка лежит той же отметкой, что приходит в раздел со стороны.
//
// Строк списка здесь нет: за время отсутствия их успевает подвинуть бот, и
// показанные из памяти, они врали бы о положении дел. Помнится только выбранное
// человеком — и то, что он завёл, но итога чего ещё не услышал: черновик окна
// «Добавить вакансию» живёт до итога разбора, а положение «Отклик при
// создании» — пока открыто окно приложения; после перезапуска он выключен.
//
// Правила — чистыми функциями; держатель — руной, один на оболочку и проверки:
// связка экрана с памятью проверяется на нём, а не на подставке.

import { CONTACTS_TABS, PROFILE_TABS, SYSTEM_TABS } from './sections.js';
import { blankVacancy } from './new_vacancy.js';
import { SORTS } from './vacancies.js';
import { blankFilter } from './vacancy_filter.js';

/** Память свежего окна: первые вкладки, ни одной открытой карточки, пустой
 *  отбор и первый порядок.
 *
 *  Порядок хранится подписью, а не ключом: подписью его выбирают в меню и
 *  подписью же показывают в подсказке кнопки. */
export function sectionMemory() {
  return {
    tabs: {
      system: SYSTEM_TABS[0].key,
      profile: PROFILE_TABS[0].key,
      contacts: CONTACTS_TABS[0].key,
    },
    cards: {},
    views: {
      vacancies: { filter: blankFilter(), sort: SORTS[0].label },
    },
  };
}

/** Сменить вкладку раздела. Карточка прежней вкладки забывается: чужой номер
 *  новая вкладка приняла бы за свой. */
export function withTab(memory, section, tab) {
  if (memory.tabs[section] === tab) return memory;
  return {
    ...memory,
    tabs: { ...memory.tabs, [section]: tab },
    cards: { ...memory.cards, [section]: null },
  };
}

/** Запомнить открытую карточку раздела; пусто — ничего не открыто. */
export function withCard(memory, section, card) {
  return { ...memory, cards: { ...memory.cards, [section]: card } };
}

/** Запомнить отбор и порядок списка раздела. */
export function withView(memory, section, view) {
  return { ...memory, views: { ...memory.views, [section]: view } };
}

/** Держатель памяти: что запомнено и как запомнить новое. */
export function heldMemory() {
  let memory = $state(sectionMemory());
  // Окно заведения правит черновик на месте его полей, поэтому он держится
  // руной целиком, а не сменой памяти, как отбор и вкладки. `handed` — черновик
  // ушёл боту и его итог ещё не принят: закрытое окно его не стирает, даже если
  // отказ пришёл вестью раньше ответа на сам зов.
  const newVacancy = $state({ draft: blankVacancy(), handsOver: false, handed: false });
  return {
    newVacancy,
    get tabs() {
      return memory.tabs;
    },
    get cards() {
      return memory.cards;
    },
    get views() {
      return memory.views;
    },
    pickTab: (key) => (tab) => (memory = withTab(memory, key, tab)),
    remember: (key) => (card) => (memory = withCard(memory, key, card)),
    keepView: (key) => (view) => (memory = withView(memory, key, view)),
  };
}
