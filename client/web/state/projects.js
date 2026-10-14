// Проекты, переведённые в то, что видно и что набирают.
//
// Проект — место работы без должности и дат, с одним перечнем «О проекте».
// Чистые функции; ни моста, ни разметки этот файл не знает.

import { recordsGoing } from './records.js';
import { counted } from './words.js';

/** Какие обязательные поля проекта пусты: обязательно одно название, как требует мост. */
export function projectMissing(project) {
  return (project.name || '').trim() ? [] : ['name'];
}

/** Готов ли проект к записи. */
export function projectReady(project) {
  return projectMissing(project).length === 0;
}

/** Что из перечня проектов уедет на мост — и почему не уедет ничего. */
export function projectsGoing(rows) {
  return recordsGoing(
    rows,
    projectReady,
    (shown, whole) =>
      `Проект #${shown}: заполните название — пока оно пусто, `
      + `${whole ? 'перечень проектов' : 'проект'} не сохраняется.`,
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
  missing: projectMissing,
  leaving: (one) => `Удалить проект «${one.name || 'без названия'}»?`,
};
