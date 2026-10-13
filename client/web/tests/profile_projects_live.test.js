// @vitest-environment jsdom
//
// Вкладка проектов: та же вкладка записей, что у мест работы, с полями проекта.

import { cleanup } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import ProjectCard from '../components/ProjectCard.svelte';
import { PROJECTS } from '../state/projects.js';
import { fill, recordsTab } from './records_tab.js';
import { settled } from './settled.js';

afterEach(cleanup);

const OLD = { id: 1, name: 'Давний', url: null, about: [], skill_names: [] };

const tab = (projects) => recordsTab(PROJECTS, ProjectCard, projects);

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

  it('пункты «О проекте» уезжают перечнем: добавленный, набранный, удалённый', async () => {
    const { sent, q } = tab([{ ...OLD, about: ['Описание'] }]);
    await settled();
    q.getByText('Давний').click();
    await settled();

    q.getByText('Добавить пункт').click();
    await settled();
    fill(q.getAllByRole('textbox').at(-1), 'Второй');
    await settled();
    expect(sent.at(-1)[0].about).toEqual(['Описание', 'Второй']);

    q.getAllByTitle('Удалить')[0].click();
    await settled();
    expect(sent.at(-1)[0].about).toEqual(['Второй']);
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
