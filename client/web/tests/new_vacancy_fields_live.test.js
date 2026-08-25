// @vitest-environment jsdom
//
// Доезжают ли перечни до подсказки, придя после того, как форма уже открыта.
//
// Порядок именно такой у живого окна: кнопка открывает форму сразу, а имена
// людей и компаний приезжают с моста следом. Проверка на готовых перечнях
// этого не ловит вовсе — она монтирует форму уже с ними.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import NewCardDialog from '../components/NewCardDialog.svelte';
import NewVacancyFields from '../components/NewVacancyFields.svelte';
import { blankVacancy } from '../state/vacancies.js';
import { livingProps } from './live_props.svelte.js';
import { settled } from './settled.js';

let mounted = null;
let host = null;

afterEach(() => {
  if (mounted) flushSync(() => unmount(mounted));
  host?.remove();
  mounted = null;
  host = null;
});

function form() {
  const [props, change] = livingProps({
    draft: blankVacancy(),
    options: { companies: [], hrs: [] },
    oncompany: () => {},
    onhr: () => {},
  });
  host = document.createElement('div');
  document.body.append(host);
  mounted = mount(NewVacancyFields, { target: host, props });
  return { change, host };
}

describe('живые поля новой вакансии', () => {
  it('подсказка показывает имена, приехавшие после открытия формы', async () => {
    const { change, host } = form();
    await settled();

    change('options', { companies: [], hrs: ['Polyy', 'Yana'] });
    await settled();

    const hr = host.querySelector('input[placeholder="HR"]');
    hr.dispatchEvent(new Event('focus'));
    await settled();

    expect(host.textContent).toContain('Polyy');
  });

  it('и когда перечни едут через окно заведения, а не прямо в поля', async () => {
    // Окно стоит между экраном и полями: перечни идут через него разметкой, и
    // застрянь они там, поля остались бы с пустыми подсказками навсегда.
    const [props, change] = livingProps({
      kind: 'vacancy',
      draft: blankVacancy(),
      busy: false,
      ready: false,
      options: { companies: [], hrs: [] },
      oncompany: () => {},
      onhr: () => {},
      onconfirm: () => {},
      oncancel: () => {},
    });
    host = document.createElement('div');
    document.body.append(host);
    mounted = mount(NewCardDialog, { target: host, props });
    await settled();

    change('options', { companies: [], hrs: ['Polyy', 'Yana'] });
    await settled();

    const hr = host.querySelector('input[placeholder="HR"]');
    hr.dispatchEvent(new Event('focus'));
    await settled();

    expect(host.textContent).toContain('Polyy');
  });
});
