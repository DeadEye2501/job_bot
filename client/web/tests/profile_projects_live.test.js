// @vitest-environment jsdom
//
// Вкладка проектов: та же вкладка записей, что у мест работы, с полями проекта.

import { cleanup, render, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import ProfileRecords from '../app/ProfileRecords.svelte';
import ProjectCard from '../components/ProjectCard.svelte';
import { PROJECTS } from '../state/projects.js';
import { settled } from './settled.js';

afterEach(cleanup);

const OLD = { id: 1, name: 'Давний', url: null, about: [], skill_names: [] };

/** Вкладка с записанными за ней посылками на мост. */
function tab(projects = []) {
  const sent = [];
  const ask = async (method, payload) => {
    if (method === 'profile.projects') return { projects, skills_index: [] };
    if (method === 'profile.save_projects') {
      sent.push(payload.projects);
      return {};
    }
    return {};
  };
  const shown = render(ProfileRecords, { props: { ask, kind: PROJECTS, Card: ProjectCard } });
  return { sent, q: within(shown.container) };
}

/** Набрать в поле и отпустить его: поля карточки отправляют по уходу фокуса. */
function fill(field, value) {
  field.value = value;
  field.dispatchEvent(new Event('input', { bubbles: true }));
  field.dispatchEvent(new Event('blur', { bubbles: true }));
}

describe('живая вкладка проектов', () => {
  it('новый проект встаёт первым и уезжает с одним названием', async () => {
    const { sent, q } = tab([OLD]);
    await settled();

    q.getByText('+ Добавить проект').click();
    await settled();
    fill(q.getByPlaceholderText('Название проекта'), 'Свежий');
    await settled();

    expect(sent.at(-1).map((one) => one.name)).toEqual(['Свежий', 'Давний']);
  });

  it('у карточки проекта нет должности и дат, есть «О проекте» и стек', async () => {
    const { q } = tab();
    await settled();

    q.getByText('+ Добавить проект').click();
    await settled();

    expect(q.queryByPlaceholderText('Должность')).toBeNull();
    expect(q.queryAllByPlaceholderText('дд.мм.гггг')).toHaveLength(0);
    expect(q.getByText('О проекте')).toBeTruthy();
    expect(q.getByText('Стек')).toBeTruthy();
  });
});
