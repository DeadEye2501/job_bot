// Следствия действий над вакансией: что заперто и чем подписан исходный текст.

import { describe, expect, it } from 'vitest';

import {
  actionBlocks,
  applyChoices,
  rawChips,
  sourcePill,
} from '../state/vacancy_actions.js';

const CARD = {
  hr: { id: 1, name: 'Иван', telegram_username: 'ivan' },
  raw_text: 'Ищем питониста',
  channel_username: 'jobs',
  source_msg_id: 42,
  source_url: 'https://t.me/jobs/42',
  posted_at: '2026-08-14T06:05:00+00:00',
  created_at: '2026-08-15T17:00:00+00:00',
};

describe('запреты действий', () => {
  it('всё живо и HR привязан — не заперто ничего', () => {
    expect(actionBlocks(CARD, '')).toEqual({ send: '', rerun: '', source: '', raw: '' });
  });

  it('без исходного текста показывать нечего, и пункт заперт', () => {
    // Заведённая полями вакансия исходника не имеет вовсе: описание к ней
    // пишет человек, а не автор объявления. Окно с пустым текстом открывается
    // и выглядит поломкой — заслон объясняет, что смотреть нечего.
    expect(actionBlocks({ ...CARD, raw_text: null }, '').raw).toBe(
      'У вакансии нет исходного текста',
    );
  });

  it('без HR отклик не заперт: откликнуться можно и не в Telegram', () => {
    // Куда откликаться, решает окно выбора по ответу моста: у вакансии с сайта
    // HR нет, а форма и почта есть.
    expect(actionBlocks({ ...CARD, hr: null }, '').send).toBe('');
  });

  it('неживое окружение запирает оба, и сказано об этом теми же словами', () => {
    // Обе просьбы уходят боту: отправка сочиняет письмо моделью, разбор ею же
    // разбирает. Своя фраза здесь спорила бы с той, что уже висит на кнопке
    // обхода внизу окна.
    const blocks = actionBlocks(CARD, 'Модель не отвечает');
    expect(blocks).toMatchObject({ send: 'Модель не отвечает', rerun: 'Модель не отвечает' });
  });

  it('идущий обход запирает и отклик, и переразбор', () => {
    // Оба зовут модель, а прогон зовёт её сам: параллельной работы модели не
    // допускаем — даже отклик в Telegram, которому браузер не нужен.
    expect(actionBlocks(CARD, '', true)).toMatchObject({
      send: 'Идёт обход',
      rerun: 'Идёт обход',
    });
  });

  it('обход старше погасшей лампы — то же старшинство, что у окна заведения и источников', () => {
    // Правило запора одно на окно и кнопки карточки: разные старшинства у
    // одних кнопок бота читались бы двумя правдами об одном.
    expect(actionBlocks(CARD, 'Модель не отвечает', true).send).toBe('Идёт обход');
  });

  it('без ссылки на источник переход к посту заперт', () => {
    // Ссылку кладёт сбор, и приходит она не от всякого источника. Живой пункт
    // меню обещает переход, которого не будет: человек нажимает и ничего не
    // происходит.
    expect(actionBlocks({ ...CARD, source_url: null }, '').source)
      .toBe('Нет ссылки на источник');
  });

  it('со ссылкой переход не заперт', () => {
    expect(actionBlocks(CARD, '').source).toBe('');
  });

  it('пустой исходный текст переразбора не запирает', () => {
    // Запирает его только неживое окружение: разбор зовут как раз тогда, когда
    // карточка вышла кривой, и заслон здесь отнимал бы единственный способ
    // это поправить. Отказ мост скажет сам, если разбирать и правда нечего.
    expect(actionBlocks({ ...CARD, raw_text: null }, '').rerun).toBe('');
  });
});

describe('чипы исходного текста', () => {
  it('называют канал, номер сообщения, время поста и длину', () => {
    // По ним объявление находят в самом Telegram, когда разбор вышел кривым.
    expect(rawChips(CARD)).toEqual([
      { icon: 'tag', text: '@jobs' },
      { icon: 'numbers', text: 'msg #42' },
      { icon: 'schedule', text: '2026-08-14 09:05' },
      { icon: 'straighten', text: '14 символов' },
    ]);
  });

  it('у поста без своей метки времени берут время записи', () => {
    // Метку ставит канал, и приходит она не от всякого источника; время
    // заведения записи хотя бы обозначает, когда объявление к нам попало.
    const chips = rawChips({ ...CARD, posted_at: null });
    expect(chips).toContainEqual({ icon: 'schedule', text: '2026-08-15 20:00' });
  });

  it('число символов согласовано со словом', () => {
    expect(rawChips({ ...CARD, raw_text: 'а' })).toContainEqual({
      icon: 'straighten',
      text: '1 символ',
    });
    expect(rawChips({ ...CARD, raw_text: 'абв' })).toContainEqual({
      icon: 'straighten',
      text: '3 символа',
    });
  });

  it('несохранённый исходный текст считается пустым, а не роняет полосу', () => {
    // Окно исходного текста открывают и у такой вакансии — сказать, что
    // показывать нечего; обращение к длине пустоты уронило бы само окно.
    expect(rawChips({ ...CARD, raw_text: null })).toContainEqual({
      icon: 'straighten',
      text: '0 символов',
    });
  });

  it('без канала, номера и времени остаётся одна длина', () => {
    // Канал могли снести, а номер и метка приходят не от всякого источника:
    // пустые чипы читались бы как потерянные поля.
    const chips = rawChips({
      ...CARD,
      channel_username: null,
      source_msg_id: null,
      posted_at: null,
      created_at: null,
    });
    expect(chips).toEqual([{ icon: 'straighten', text: '14 символов' }]);
  });

  it('у вакансии с агрегатора первым назван агрегатор', () => {
    const chips = rawChips({ ...CARD, channel_username: null, aggregator_name: 'Пример' });
    expect(chips[0]).toEqual({ icon: 'language', text: 'Пример' });
  });
});

describe('пилюля источника в шапке карточки', () => {
  it('у вакансии из канала — канал и переход к посту', () => {
    expect(sourcePill(CARD)).toEqual({ icon: 'tag', text: 'jobs', title: 'Перейти к посту в канале' });
  });

  it('у вакансии с агрегатора — агрегатор и переход к вакансии на сайте', () => {
    // Источник любой вакансии виден одинаково: пилюля заполняется сама, по
    // привязке, и по нажатию ведёт туда, откуда вакансия пришла.
    const card = { ...CARD, channel_username: null, aggregator_name: 'Пример' };
    expect(sourcePill(card)).toEqual({ icon: 'language', text: 'Пример', title: 'Перейти к вакансии на сайте' });
  });

  it('у вакансии из поиска по сети — «Сайт», а не имя поиска', () => {
    // «Поиск по сети» — способ, которым её нашли, а не место, откуда она:
    // пришла она с сайта компании или чужой доски.
    const card = { ...CARD, channel_username: null, aggregator_name: 'Поиск по сети', from_web_search: true };
    expect(sourcePill(card).text).toBe('Сайт');
    expect(rawChips(card)[0]).toEqual({ icon: 'language', text: 'Сайт' });
  });

  it('у вакансии без источника пилюли нет', () => {
    // Вставленная текстом или заведённая руками: пустая пилюля читалась бы как
    // потерянный источник.
    expect(sourcePill({ ...CARD, channel_username: null, aggregator_name: null })).toBeNull();
  });
});

describe('способы отклика в окне выбора', () => {
  const MAIL = { method: 'email', target: 'hr@example.com' };

  it('способы приходят строками окна как есть, Telegram среди них', () => {
    const rows = applyChoices({ ways: [
      { method: 'telegram', target: '@hr_name' },
      { method: 'email', target: 'hr@company.test' },
    ] });
    expect(rows.map((r) => r.contact)).toEqual(['@hr_name', 'hr@company.test']);
    expect(rows.every((r) => r.way)).toBe(true);
  });

  it('способ несёт то, что мост ждёт обратно', () => {
    const [row] = applyChoices({ ways: [MAIL] });
    expect(row.way).toEqual(MAIL);
  });

  it('ключи строк разные и у двух адресов одного способа', () => {
    const other = { method: 'email', target: 'boss@example.com' };
    const rows = applyChoices({ ways: [MAIL, other] });
    expect(new Set(rows.map((row) => row.key)).size).toBe(2);
  });
});
