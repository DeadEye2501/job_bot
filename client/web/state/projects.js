// Проекты, переведённые в то, что видно и что набирают.
//
// Проект — место работы без должности и дат, с одним перечнем «О проекте».
// Чистые функции; ни моста, ни разметки этот файл не знает.

import { recordsGoing } from './records.js';
import { counted } from './words.js';

/** Готов ли проект к записи: обязательно одно название, как требует мост. */
export function projectReady(project) {
  return Boolean((project.name || '').trim());
}

/** Что из перечня проектов уедет на мост — и почему не уедет ничего. */
export function projectsGoing(rows) {
  return recordsGoing(
    rows,
    projectReady,
    (shown) => `Проект #${shown}: заполните название — пока оно пусто, перечень не записывается.`,
  );
}

/** Чем подписана свёрнутая карточка: дат и должности у проекта нет. */
export function projectTitle(project) {
  return { name: project.name || 'Без названия', role: '', period: '' };
}

/** Проекты как вид записи вкладки профиля. */
export const PROJECTS = {
  key: 'projects',
  heading: 'Профиль / Projects',
  count: (n) => counted(n, 'проект', 'проекта', 'проектов'),
  addLabel: '+ Добавить проект',
  blank: () => ({ id: null, name: '', url: '', about: [], skill_names: [] }),
  going: projectsGoing,
  leaving: (one) => `Удалить проект «${one.name || 'без названия'}»?`,
};
