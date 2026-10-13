// Живая вкладка записей анкеты — мест работы или проектов — для проверок.
//
// Вкладка одна на оба вида, и монтируется она одинаково: свой вид записи, своя
// карточка, а мост подставной — отдаёт заданный перечень и копит посылки.

import { render, within } from '@testing-library/svelte';

import ProfileRecords from '../app/ProfileRecords.svelte';

/** Вкладка вида `kind` с карточкой `Card` и перечнем `rows` от моста. */
export function recordsTab(kind, Card, rows = []) {
  const sent = [];
  const load = async () => ({ [kind.key]: rows, skills_index: [] });
  const save = async (going) => {
    sent.push(going);
    return {};
  };
  const shown = render(ProfileRecords, { props: { load, save, kind, Card } });
  return { sent, q: within(shown.container) };
}

/** Набрать в поле и отпустить его: поля карточки отправляют по уходу фокуса. */
export function fill(field, value) {
  field.value = value;
  field.dispatchEvent(new Event('input', { bubbles: true }));
  field.dispatchEvent(new Event('blur', { bubbles: true }));
}
