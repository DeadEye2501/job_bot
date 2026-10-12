// @vitest-environment jsdom
//
// Нижняя полоса как своя сборка.
//
// Жила она внутри оболочки — вместе с боковым меню и полем раздела, — и её
// десять состояний с десятью объявлениями делали самый большой файл фронта
// единственной точкой, которую правят и при добавлении раздела, и при любой
// правке полосы.
//
// Своей работы у полосы две, и обе видны только отсюда: часы здоровья, по
// которым зажигаются лампочки, и подсказка о запертых кнопках, которую ждут
// наверху — её раздают экранам.

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';

import BottomBar from '../app/BottomBar.svelte';
import { applyNote } from '../state/progress.js';
import { hearRound } from '../state/round.svelte.js';
import { answering } from './bridge_stub.js';
import { settled } from './settled.js';

afterEach(cleanup);

// `counts` — что по очереди отвечает число новых вакансий; последнее держится.
// `app` — запущенная версия и может ли копия обновиться; `updates` — что по
// очереди отвечает проверка обновления, последнее держится.
function bar(health, counts = [0], { app = null, updates = [{ newer: null, trouble: null }] } = {}) {
  const tips = [];
  // Плашки полоса показывает не через мост, а через `say`: отказ запертого
  // тумблера виден только здесь.
  const said = [];
  // Вести полосе приходят подпиской: сюда складываются обработчики, чтобы
  // проверка могла позвать их так же, как их зовёт мост.
  const handlers = {};
  const left = [...counts];
  const checks = [...updates];
  const { asked, ask } = answering((method, payload) => {
    if (method === 'system.initial') return { unread: { count: 0 }, mode: 'Full', health };
    if (method === 'system.set_mode') return { mode: payload };
    if (method === 'system.health') return health;
    if (method === 'system.new_vacancies') return { count: left.length > 1 ? left.shift() : left[0] };
    if (method === 'system.check_update') return checks.length > 1 ? checks.shift() : checks[0];
    return {};
  });

  const events = {
    on: (name, handler) => {
      handlers[name] = handler;
      return () => {};
    },
    run: () => {},
    stop: () => {},
  };
  // Вести о начале и конце прогона слушает общий учёт, а не полоса: в окне его
  // подписывает оболочка, здесь — проверка, на те же поддельные вести.
  hearRound(events);

  render(BottomBar, {
    props: {
      ask,
      say: (text) => said.push(text),
      events,
      onlocked: (tip) => tips.push(tip),
      oncontact: () => {},
      app,
    },
  });
  return { asked, tips, said, handlers };
}

describe('живая нижняя полоса', () => {
  it('разбор вставленного объявления называет себя под полосами', async () => {
    // Ступень эта счёта не имеет — полосы бегут пустыми, — и своё имя говорит
    // подписью. Не разбери полоса стадию, человек читал бы «Запуск…» всё
    // время разбора и не отличил бы свою вставку от обхода каналов.
    const { handlers } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    // Полоса показывает подпись только на идущей работе: до вести о начале
    // её место занято переключателем режима.
    handlers.ingestion_started();
    handlers.progress_update({
      stage: 'pasted',
      label: 'Разбор вставленного объявления…',
      current: 0,
      total: 0,
    });
    await settled();

    expect(document.body.textContent).toContain('Разбор вставленного объявления…');
  });

  it('гасит бота, когда что-то отвалилось, и называет наверх причину', async () => {
    // Бот, работающий против мёртвой системы, крутит обороты впустую, а
    // тумблер в этот миг уже заперт, и человек выключить его не может.
    const { asked, tips } = bar({ db: true, tg: false, chat: true, embed: true });
    await settled();

    expect(asked.some((one) => one.method === 'system.set_mode' && one.payload === 'Off')).toBe(true);
    expect(tips.at(-1)).toContain('TG');
  });

  it('запертый тумблер режима не переключает, а объясняет отказ', async () => {
    // Пока не жива хоть одна система, работать боту нечем, и смена режима
    // отдала бы человеку тумблер, за которым ничего не происходит. Молчать
    // при этом нельзя: запертую кнопку жмут именно затем, чтобы узнать почему.
    const { asked, said } = bar({ db: true, tg: false, chat: true, embed: true });
    await settled();
    const before = asked.filter((one) => one.method === 'system.set_mode').length;

    document.querySelector('.mode-control').click();
    await settled();

    expect(asked.filter((one) => one.method === 'system.set_mode')).toHaveLength(before);
    expect(said.at(-1)).toContain('TG');
  });

  it('при живых системах бота не трогает и подсказку отдаёт пустой', async () => {
    const { asked, tips } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    expect(asked.some((one) => one.method === 'system.set_mode')).toBe(false);
    expect(tips.at(-1)).toBe('');
  });

  it('ожидание человека встаёт плашкой на место полос', async () => {
    const { handlers } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    handlers.ingestion_started();
    handlers.human_needed({ kind: 'captcha', host: 'site.test' });
    await settled();

    expect(document.querySelector('.human-plate').textContent).toContain('Требуется пройти капчу');
    expect(document.querySelector('.progress-wrap')).toBeNull();
  });

  it('нажатие на плашку выводит браузер, галочка отпускает агента', async () => {
    const { asked, handlers } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();
    handlers.ingestion_started();
    handlers.human_needed({ kind: 'captcha', host: 'site.test' });
    await settled();

    document.querySelector('.human-plate-text').click();
    document.querySelector('.human-plate-done').click();
    await settled();

    const methods = asked.map((one) => one.method);
    expect(methods).toContain('system.reveal_browser');
    expect(methods).toContain('system.human_done');
  });

  it('ход обхода агрегатора идёт полосой каналов, со счётом в скобках', async () => {
    const { handlers } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    handlers.ingestion_started();
    handlers.progress_update({ stage: 'aggregator', label: 'hh.ru — найдено', current: 3, total: 10 });
    await settled();

    expect(document.querySelector('.progress-caption').textContent).toContain('hh.ru — найдено (3/10)');
  });

  it('ступень отклика видна подписью', async () => {
    expect(applyNote({ label: 'Python-разработчик', current: 0, total: 3 }))
      .toBe('Python-разработчик — отклик (1/3)');
  });

  it('ход откликов виден под полосами', async () => {
    const { handlers } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    handlers.ingestion_started();
    handlers.progress_update({ stage: 'apply', label: 'Python-разработчик', current: 1, total: 3 });
    await settled();

    expect(document.querySelector('.progress-caption').textContent)
      .toContain('Python-разработчик — отклик (2/3)');
  });

  it('слово обхода показывается плашкой', async () => {
    const { handlers, said } = bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    handlers.round_note({ text: 'Капча не пройдена — обход снят.' });

    expect(said).toContain('Капча не пройдена — обход снят.');
  });
});

describe('счётчик непрочитанного', () => {
  it('при нуле заперт, как прочие значки, и говорит, что сообщений нет', async () => {
    bar({ db: true, tg: true, chat: true, embed: true });
    await settled();

    const badge = document.querySelector('.badge-unread');
    expect(badge.getAttribute('aria-disabled')).toBe('true');
    expect(badge.title).toBe('Новых сообщений нет');
  });
});

describe('переключатель режима без слова', () => {
  it('наведение на треть дорожки называет режим, который она включит', async () => {
    bar({ db: true, tg: true, chat: true, embed: true });
    await settled();
    const toggle = document.querySelector('.mode-control');
    // У jsdom раскладки нет: дорожку меряем сами, как её мерил бы браузер.
    document.querySelector('.mode-track').getBoundingClientRect = () => ({ left: 0, width: 300 });

    toggle.dispatchEvent(new MouseEvent('mousemove', { clientX: 150, bubbles: true }));
    await settled();

    expect(toggle.title).toBe('Только приём сообщений от HR');
  });

  it('запертый говорит, почему заперт, а не что включит', async () => {
    const { tips } = bar({ db: true, tg: false, chat: true, embed: true });
    await settled();
    const toggle = document.querySelector('.mode-control');
    document.querySelector('.mode-track').getBoundingClientRect = () => ({ left: 0, width: 300 });

    toggle.dispatchEvent(new MouseEvent('mousemove', { clientX: 150, bubbles: true }));
    await settled();

    expect(toggle.title).toBe(tips.at(-1));
  });
});

describe('значок «отклик на все новые»', () => {
  const ALIVE = { db: true, tg: true, chat: true, embed: true };
  const icon = () => document.querySelector('.apply-all-btn');

  it('без новых вакансий серый и не нажимается', async () => {
    const { asked } = bar(ALIVE, [0]);
    await settled();

    expect(icon().getAttribute('aria-disabled')).toBe('true');
    expect(icon().classList.contains('lit')).toBe(false);
    expect(icon().title).toBe('Новых вакансий для отклика нет');
    icon().click();
    await settled();
    expect(asked.map((one) => one.method)).not.toContain('system.apply_all_new');
  });

  it('с новыми — жёлтый, с числом в подсказке, нажатие пускает отклики', async () => {
    const { asked } = bar(ALIVE, [3]);
    await settled();

    expect(icon().getAttribute('aria-disabled')).toBe('false');
    expect(icon().classList.contains('lit')).toBe(true);
    expect(icon().title).toBe('Откликнуться на все новые вакансии: 3');
    icon().click();
    await settled();
    expect(asked.map((one) => one.method)).toContain('system.apply_all_new');
  });

  it('пока идёт прогон, заперт', async () => {
    const { asked, handlers } = bar(ALIVE, [3]);
    await settled();

    handlers.ingestion_started();
    await settled();

    expect(icon().getAttribute('aria-disabled')).toBe('true');
    icon().click();
    await settled();
    expect(asked.map((one) => one.method)).not.toContain('system.apply_all_new');
  });

  it('перемена в списке вакансий перечитывает число', async () => {
    const { handlers } = bar(ALIVE, [3, 0]);
    await settled();

    handlers.vacancies_list_changed();
    await settled();

    expect(icon().classList.contains('lit')).toBe(false);
    expect(icon().getAttribute('aria-disabled')).toBe('true');
  });

  it('стоит перед переключателем режима', async () => {
    bar(ALIVE, [3]);
    await settled();

    const right = [...document.querySelector('.bb-right').children];
    expect(right).toContain(icon());
    expect(right.indexOf(icon())).toBe(right.indexOf(document.querySelector('.mode-control')) - 1);
  });
});

describe('значок обновления', () => {
  const ALIVE = { db: true, tg: true, chat: true, embed: true };
  const BUILT = { version: '1.0.0', updatable: true };
  const NOTHING = { newer: null, trouble: null };
  const SILENT = { newer: null, trouble: 'GitHub не ответил — проверьте связь.' };
  const READY = { newer: '1.1.0', trouble: null };
  const icon = () => document.querySelector('.update-btn');
  const methods = (asked) => asked.map((one) => one.method);

  it('у копии из исходников проверяет так же, а найденную версию не качает — подменять нечего', async () => {
    const { asked } = bar(ALIVE, [0], { app: { version: '1.0.0', updatable: false }, updates: [READY] });
    await settled();

    expect(methods(asked)).toContain('system.check_update');
    expect(icon().classList.contains('lit')).toBe(true);
    expect(icon().title).toBe('Обновить приложение');
    expect(icon().getAttribute('aria-disabled')).toBe('true');
    icon().click();
    await settled();
    expect(methods(asked)).not.toContain('system.update');
  });

  it('при запуске проверяет молча: серый, «Проверить обновления», без плашки', async () => {
    const { asked, said } = bar(ALIVE, [0], { app: BUILT, updates: [SILENT] });
    await settled();

    expect(methods(asked)).toContain('system.check_update');
    expect(icon().classList.contains('lit')).toBe(false);
    expect(icon().title).toBe('Проверить обновления');
    expect(said).toEqual([]);
  });

  it('нажатие серого проверяет и говорит, что версия последняя', async () => {
    const { said } = bar(ALIVE, [0], { app: BUILT, updates: [NOTHING] });
    await settled();

    icon().click();
    await settled();

    expect(said).toContain('Установлена последняя версия, v1.0.0');
  });

  it('по нажатию беда сети говорится словами', async () => {
    const { said } = bar(ALIVE, [0], { app: BUILT, updates: [NOTHING, SILENT] });
    await settled();

    icon().click();
    await settled();

    expect(said).toContain('GitHub не ответил — проверьте связь.');
  });

  it('найденная версия — акцентный значок, нажатие качает её', async () => {
    const { asked } = bar(ALIVE, [0], { app: BUILT, updates: [READY] });
    await settled();

    expect(icon().classList.contains('lit')).toBe(true);
    expect(icon().title).toBe('Обновить приложение');
    icon().click();
    await settled();
    expect(methods(asked)).toContain('system.update');
  });

  it('пока идёт прогон, обновиться нельзя', async () => {
    const { asked, handlers } = bar(ALIVE, [0], { app: BUILT, updates: [READY] });
    await settled();

    handlers.ingestion_started();
    await settled();

    expect(icon().getAttribute('aria-disabled')).toBe('true');
    icon().click();
    await settled();
    expect(methods(asked)).not.toContain('system.update');
  });

  it('стоит перед значком «!»', async () => {
    bar(ALIVE, [0], { app: BUILT });
    await settled();

    const right = [...document.querySelector('.bb-right').children];
    expect(right).toContain(icon());
    expect(right.indexOf(icon())).toBe(right.indexOf(document.querySelector('.apply-all-btn')) - 1);
  });

  it('ход скачивания — верхняя полоса и подпись в мегабайтах', async () => {
    const { handlers } = bar(ALIVE, [0], { app: BUILT });
    await settled();

    handlers.ingestion_started();
    handlers.progress_update({ stage: 'update', label: 'Обновление', current: 1048576, total: 2097152 });
    await settled();

    expect(document.querySelector('.progress-caption').textContent).toBe('Обновление — 1 из 2 МБ');
    expect(document.querySelector('.progress-fill').getAttribute('style')).toContain('width: 50%');
  });

  it('в конце скачивания числа подписи сходятся', async () => {
    // Скачанное и итог округляются одним правилом: иначе полный файл читался
    // бы как «94 из 95 МБ» — будто не докачан.
    const { handlers } = bar(ALIVE, [0], { app: BUILT });
    await settled();

    handlers.ingestion_started();
    handlers.progress_update({ stage: 'update', label: 'Обновление', current: 99000000, total: 99000000 });
    await settled();

    expect(document.querySelector('.progress-caption').textContent).toBe('Обновление — 94 из 94 МБ');
  });

  it('у запертого значка подсказки нет: обещать то, что не нажмётся, незачем', async () => {
    const { handlers } = bar(ALIVE, [0], { app: BUILT, updates: [READY] });
    await settled();

    handlers.ingestion_started();
    await settled();

    expect(icon().title).toBe('');
  });

  it('после прогона найденная версия переспрашивается молча', async () => {
    // Релиз могли отозвать, а скачивание ответить «новой версии нет»: значок не
    // должен звать обновиться к тому, чего уже нет.
    const { handlers } = bar(ALIVE, [0], { app: BUILT, updates: [READY, NOTHING] });
    await settled();

    handlers.ingestion_started();
    handlers.ingestion_finished();
    await settled();

    expect(icon().classList.contains('lit')).toBe(false);
  });
});

describe('кнопка запуска на прогоне', () => {
  it('«Стоп» не заперт и при погасшей лампе: идущую работу всегда можно остановить', async () => {
    const { handlers } = bar({ db: true, tg: true, chat: false, embed: true });
    await settled();

    handlers.ingestion_started();
    await settled();

    expect(document.querySelector('.run-btn').getAttribute('aria-disabled')).toBe('false');
  });
});

