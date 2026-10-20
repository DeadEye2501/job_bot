// @vitest-environment jsdom
//
// Следствия шага «Резюме», пока идёт разбор: чем он кончается и что человек
// успевает нажать, пока ждёт.
//
// Разбор — единственная работа мастера, идущая минутами, и единственная, чей
// исход приходит вестью, а не возвратом зова. Шаг всё это время стоит на месте,
// и всё, что человек на нём трогает, он трогает посреди работы.

import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import WizardCv from '../app/WizardCv.svelte';
import { hearAwaited } from '../state/awaited.svelte.js';
import { listening } from './bridge_stub.js';
import { settled } from './settled.js';

let deaf = () => {};

afterEach(() => {
  cleanup();
  deaf();
});

const ANSWERS = {
  'profile.get': {
    cv_meta: { name: 'резюме.pdf', size: 1024, exists: true },
    cv_path: 'C:/резюме.pdf',
  },
  'profile.parse_cv': { started: true },
};

/** Шаг с подставным мостом: след зовов и способ доставить весть об исходе.
 *
 * Вести слушает учёт ожиданий, как в оболочке; весть доставляется с меткой
 * разбора резюме — чужие шаг не ловит. `during` доставляет весть посреди самого
 * зова разбора — так приходят мгновенные отказы: файл пропал, формат не
 * читается, текста в файле нет.
 */
function step(during = null) {
  const trail = [];
  const events = listening();
  deaf = hearAwaited(events);
  const finished = (payload) => events.fire('action_finished', { action: 'parse_cv', ...payload });
  render(WizardCv, {
    props: {
      ask: async (path) => {
        trail.push(path);
        if (path === 'profile.parse_cv' && during) finished(during);
        return ANSWERS[path];
      },
      busy: false,
      onback: () => {},
      onnext: async () => {
        trail.push('ушли дальше');
      },
    },
  });
  return { trail, finished };
}

/** Выбрать разбор и нажать «Готово», дождавшись, что работа пущена. */
async function parsing(trail) {
  const done = screen.getByRole('button', { name: /Готово/ });
  await vi.waitFor(() => expect(done.disabled).toBe(false));
  screen.getAllByRole('radio')[0].click();
  done.click();
  await vi.waitFor(() => expect(trail).toContain('profile.parse_cv'));
}

describe('живой шаг резюме', () => {
  it('взятый файл назван строкой резюме с размером, и его можно заменить', async () => {
    step();

    await vi.waitFor(() => expect(screen.getByText('резюме.pdf')).toBeTruthy());
    expect(screen.getByText('1 КБ')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Заменить' })).toBeTruthy();
  });

  it('удавшийся разбор уводит шаг дальше', async () => {
    const { trail, finished } = step();
    await parsing(trail);

    finished({ message: 'Резюме разобрано', danger: false });

    await vi.waitFor(() => expect(trail).toContain('ушли дальше'));
  });

  it('нажатия по карточкам во время разбора не вешают шаг', async () => {
    // Заперт не только подвал, но и сами карточки: отопри их, и выбор,
    // сменённый посреди работы, увёл бы человека с шага, на котором он ждёт
    // разбора, — а анкета к тому времени уже заменена.
    const { trail, finished } = step();
    await parsing(trail);

    screen.getAllByRole('radio')[2].click();
    finished({ message: 'Резюме разобрано', danger: false });

    await vi.waitFor(() => expect(trail).toContain('ушли дальше'));
  });

  it('мгновенный отказ не затирается надписью о работе', async () => {
    // Пропавший файл и нечитаемый формат отвечают вестью раньше, чем зов
    // разбора успевает вернуться. Скажи шаг «разбираем» после этого — человек
    // читал бы о работе, которой уже нет, и ждал бы её конца впустую.
    const { trail } = step({
      message: 'Файл резюме не найден — выберите его заново.',
      danger: true,
    });
    await parsing(trail);

    await vi.waitFor(() => expect(screen.getByText(/не найден/)).toBeTruthy());
    expect(screen.queryByText(/Разбираем резюме/)).toBeNull();
  });

  it('чужая весть шаг не уводит', async () => {
    const { trail, finished } = step();
    await parsing(trail);

    finished({ action: 'rerun', message: 'Вакансия разобрана заново', danger: false });
    await settled();

    expect(trail).not.toContain('ушли дальше');
  });

  it('сорвавшийся разбор возвращает шаг с причиной', async () => {
    const { trail, finished } = step();
    await parsing(trail);

    finished({ message: 'В файле нет текста — похоже, это скан.', danger: true });

    await vi.waitFor(() => expect(screen.getByText(/это скан/)).toBeTruthy());
    expect(trail).not.toContain('ушли дальше');
  });
});
