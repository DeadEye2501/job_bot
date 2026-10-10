// @vitest-environment jsdom
//
// Экран настроек над мостом: лимит вакансий с агрегатора в строке «Пайплайн» и
// почта для откликов.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import SettingsScreen from '../app/SettingsScreen.svelte';
import { settled } from './settled.js';

afterEach(cleanup);

const CREDS = { base_url: '', api_key: '', model: '' };

const SNAPSHOT = {
  tg: { api_id: '', api_hash: '', phone: '', has_password: false, has_session: false, username: '' },
  chat: CREDS,
  embed: CREDS,
  pipeline: {
    scoring_threshold: 5,
    poll_interval_sec: 60,
    backfill_limit: 50,
    dm_backfill_limit: 20,
    send_locked: false,
  },
  aggregators: { aggregator_backfill_limit: 20, show_browser: false, letter_writer: 'app' },
};

const NO_MAIL = {
  address: null,
  smtp_host: null,
  smtp_port: null,
  password: '',
  server_by_address: false,
};

/** Экран над мостом; `mail` — что мост отдаёт о почте. */
function screen(mail = NO_MAIL) {
  const asked = [];
  const shown = render(SettingsScreen, {
    props: {
      ask: async (method, payload) => {
        asked.push([method, payload]);
        if (method === 'settings.get') return SNAPSHOT;
        if (method === 'settings.mail') return mail;
        return {};
      },
      say: () => {},
    },
  });
  const field = (label) =>
    [...shown.container.querySelectorAll('.pipeline-row > div')]
      .find((one) => one.querySelector('.pipeline-label')?.textContent === label)
      ?.querySelector('input');
  const byHolder = (text) => shown.container.querySelector(`input[placeholder="${text}"]`);
  return { asked, field, byHolder, text: () => shown.container.textContent };
}

function leave(input, value) {
  input.value = value;
  input.dispatchEvent(new Event('blur'));
}

describe('лимит вакансий с агрегатора', () => {
  it('показывает записанное в настройках агрегаторов', async () => {
    const { field } = screen();
    await settled();

    expect(field('Вакансий с агрегатора').value).toBe('20');
  });

  it('уходит тем же сохранением настроек приложения, зажатым в границы', async () => {
    const { asked, field } = screen();
    await settled();

    leave(field('Вакансий с агрегатора'), '9999');
    await settled();

    expect(asked).toContainEqual(['settings.save', { app: { aggregator_backfill_limit: 500 } }]);
  });
});

describe('почта для откликов', () => {
  it('без почты секция говорит, что она не подключена', async () => {
    const { text } = screen();
    await settled();

    expect(text()).toContain('Не подключена');
  });

  it('с адресом, паролем и сервером называет адрес', async () => {
    const { text } = screen({
      address: 'me@yandex.ru',
      smtp_host: 'smtp.yandex.ru',
      smtp_port: 465,
      password: 'secret',
      server_by_address: true,
    });
    await settled();

    expect(text()).toContain('me@yandex.ru');
    expect(text()).not.toContain('Не подключена');
  });

  it('подключённая почта открывается с адресом и паролем точками в полях', async () => {
    const { byHolder } = screen({
      address: 'me@yandex.ru',
      password: 'secret',
      smtp_host: 'smtp.yandex.ru',
      smtp_port: 465,
      server_by_address: true,
    });
    await settled();

    expect(byHolder('Адрес почты').value).toBe('me@yandex.ru');
    const password = byHolder('Пароль приложения');
    expect([password.value, password.type]).toEqual(['secret', 'password']);
  });

  it('адрес уходит записью почты и перечитывается', async () => {
    const { asked, byHolder } = screen();
    await settled();

    leave(byHolder('Адрес почты'), ' me@yandex.ru ');
    await settled();

    expect(asked).toContainEqual([
      'settings.save_mail',
      { address: 'me@yandex.ru', password: '', smtp_host: null, smtp_port: null },
    ]);
    expect(asked.filter(([method]) => method === 'settings.mail')).toHaveLength(2);
  });

  it('поля сервера показываются, пока сервер не подставлен по адресу', async () => {
    // Вписанный руками сервер незнакомой почты держит поля на месте: иначе
    // опечатку в нём было бы негде поправить.
    const known = screen({
      address: 'me@yandex.ru',
      smtp_host: 'smtp.yandex.ru',
      smtp_port: 465,
      password: 'secret',
      server_by_address: true,
    });
    await settled();
    expect(known.byHolder('SMTP-сервер')).toBeNull();
    cleanup();

    const unknown = screen({
      address: 'me@company.test',
      smtp_host: 'smtp.company.test',
      smtp_port: 587,
      password: 'secret',
      server_by_address: false,
    });
    await settled();
    expect(unknown.byHolder('SMTP-сервер')).toBeTruthy();
    expect(unknown.byHolder('Порт')).toBeTruthy();
  });

  it('вопрос рядом с паролем объясняет, где взять пароль приложения', async () => {
    const { text } = screen();
    await settled();

    document.querySelector('button[title="Где это взять"]').click();
    await settled();

    expect(document.querySelector('.modal-dialog').textContent).toContain('Пароли приложений');
    expect(text()).toContain('Не подключена');
  });

  it('адрес в объяснении открывает сайт почты', async () => {
    const { asked } = screen();
    await settled();
    document.querySelector('button[title="Где это взять"]').click();
    await settled();

    [...document.querySelectorAll('.help-link')]
      .find((one) => one.textContent.includes('id.yandex.ru'))
      .click();
    await settled();

    expect(asked).toContainEqual(['system.open_url', 'https://id.yandex.ru/security']);
  });
});

describe('шапки секций', () => {
  /** Шапка секции с таким заголовком. */
  function head(title) {
    return [...document.querySelectorAll('.settings-section-title')].find((one) =>
      one.textContent.includes(title),
    );
  }

  it('кнопки секций стоят в шапке, справа от заголовка', async () => {
    screen();
    await settled();

    expect(head('Telegram').textContent).toContain('Войти');
    expect(head('LLM для чата').textContent).toContain('Проверить');
    expect(head('LLM для эмбеддингов').textContent).toContain('Проверить');
  });

  it('строки о сеансе Telegram под полями нет: о нём говорит плашка в шапке', async () => {
    const { text } = screen();
    await settled();

    expect(text()).not.toContain('Сессии нет');
  });
});

