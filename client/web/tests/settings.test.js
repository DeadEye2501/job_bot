// Следствия экрана настроек: что человек вводит, что видит и что уезжает на мост.
//
// Предмет — правила полей и слова состояний. Разметка проверяется глазами, а
// вот «во что превратился ввод» и «что показать про сеанс» ломаются молча.

import { describe, expect, it } from 'vitest';

import {
  BOUNDS,
  clampField,
  credsChanged,
  matchingModels,
  mirrored,
  nextStep,
  probePill,
  sameCreds,
  scorePercent,
  sessionPill,
  sessionText,
  thresholdState,
} from '../state/settings.js';

describe('числовое поле настроек', () => {
  const bounds = { ...BOUNDS.poll_interval_sec, fallback: 60 };

  it('число за границей прижимается к ней', () => {
    // Ритм опроса задан этими границами: уйди он наверх — обход не начался бы
    // в разумный срок, уйди вниз — бот пошёл бы в Telegram без передышки.
    expect(clampField('999999', bounds)).toBe(86400);
    expect(clampField('1', bounds)).toBe(10);
  });

  it('годное число проходит как есть', () => {
    expect(clampField('300', bounds)).toBe(300);
  });

  it('негодный ввод откатывается к прежнему значению', () => {
    // Пустое поле или буквы — это опечатка, а не «ноль». Прими мы её за ноль,
    // человек молча получил бы настройку, которой не задавал.
    expect(clampField('', bounds)).toBe(60);
    expect(clampField('абв', bounds)).toBe(60);
  });

  it('дробное обрезается до целого', () => {
    // Поле целочисленное: секунды с долями мост не примет.
    expect(clampField('30.7', bounds)).toBe(30);
  });
});

describe('порог отбора на дорожке', () => {
  it('доля дорожки считается от предела', () => {
    // По ней рисуется заливка. Соври она — ползунок стоял бы не там, где
    // показывает число рядом. Числа здесь свои, а не взятые из объявления:
    // сверка предела с самим собой прошла бы при любом его значении.
    expect(scorePercent(0)).toBe(0);
    expect(scorePercent(20)).toBe(100);
    expect(scorePercent(10)).toBe(50);
  });

  it('значение за пределом не выносит заливку за дорожку', () => {
    // Порог приезжает с моста и мог быть выставлен до того, как предел
    // назначили: заливка шире дорожки выглядит поломкой.
    expect(scorePercent(25)).toBe(100);
    expect(scorePercent(-3)).toBe(0);
  });
});

describe('учётные данные поставщика модели', () => {
  const creds = { base_url: 'http://localhost:1234', api_key: 'k', model: 'm' };

  it('смена любого поля считается сменой', () => {
    // По этому ответу гасится плашка проверки. Не заметь он смены — плашка
    // говорила бы «модель отвечает» про адрес, которого уже нет.
    expect(credsChanged(creds, { ...creds, base_url: 'http://other' })).toBe(true);
    expect(credsChanged(creds, { ...creds, model: 'другая' })).toBe(true);
    expect(credsChanged(creds, { ...creds, api_key: 'другой' })).toBe(true);
  });

  it('те же поля сменой не считаются', () => {
    expect(credsChanged(creds, { ...creds })).toBe(false);
  });

  it('появление или пропажа данных — тоже смена', () => {
    // Первый ответ моста приходит на пустое место, и плашку прошлой проверки
    // на нём держать не за что.
    expect(credsChanged(null, creds)).toBe(true);
    expect(credsChanged(creds, null)).toBe(true);
  });

  it('«те же, что у чата» — про адрес и ключ, но не про модель', () => {
    // Модель у эмбеддингов своя всегда: она и не может совпадать с чатовой.
    const chat = { base_url: 'http://localhost:1234', api_key: 'k', model: 'chat-model' };
    const embed = { base_url: 'http://localhost:1234', api_key: 'k', model: 'embed-model' };

    expect(sameCreds(chat, embed)).toBe(true);
    expect(sameCreds(chat, { ...embed, base_url: 'http://other' })).toBe(false);
  });

  it('без одной из сторон совпадения нет', () => {
    expect(sameCreds(null, { base_url: '', api_key: '', model: '' })).toBe(false);
  });
});

describe('плашка проверки модели', () => {
  it('удачная проверка называет модель и время ответа', () => {
    // Человек по ней понимает, что отвечает именно та модель, которую он
    // вписал, и отвечает быстро.
    expect(probePill({ status: 'ok', model: 'qwen', latencyMs: 120 }))
      .toEqual({ text: 'qwen · 120ms', tone: 'ok', title: '' });
  });

  it('беда показывается коротко, а подробность уходит в подсказку', () => {
    // Ответ провайдера бывает на десять строк: в полосе заголовка он развалил
    // бы вёрстку, а потерять его нельзя — по нему и чинят.
    expect(probePill({ status: 'err', error: 'Connection refused' }))
      .toEqual({ text: 'Ошибка', tone: 'err', title: 'Connection refused' });
  });

  it('пока проверяют — так и написано', () => {
    expect(probePill({ status: 'busy' })).toEqual({ text: 'Проверка…', tone: '', title: '' });
  });

  it('непроверенное молчит', () => {
    // Пустая плашка на непроверенном поставщике читалась бы как «что-то не
    // так», хотя не так ровно ничего.
    expect(probePill({ status: 'idle' })).toBe(null);
  });
});

describe('эмбеддинги ходят туда же, куда чат', () => {
  const chat = { base_url: 'http://localhost:1234', api_key: 'k', model: 'chat-model' };
  const embed = { base_url: 'http://other', api_key: 'иной', model: 'embed-model' };

  it('включили — адрес и ключ переезжают от чата', () => {
    // Без этого в базе осталась бы пара, которой человек на экране уже не
    // видит: поля спрятаны, а разбор вакансий ходит по старому адресу.
    expect(mirrored(chat, embed)).toEqual({
      base_url: 'http://localhost:1234',
      api_key: 'k',
      model: 'embed-model',
    });
  });

  it('модель остаётся своей', () => {
    // Модель эмбеддингов не бывает чатовой: подставь её — первый же разбор
    // вакансии ушёл бы не в ту модель и вернул мусор вместо вектора.
    expect(mirrored(chat, embed).model).toBe('embed-model');
  });
});

describe('плашка сеанса Telegram', () => {
  it('вошедший показан ником', () => {
    expect(sessionPill({ has_session: true, username: 'deadeye' }))
      .toEqual({ text: '@deadeye', tone: 'ok', title: '' });
  });

  it('сеанс есть, а ник ещё не спрошен', () => {
    // На холодном старте Telegram не успевает ответить, и «@» без имени
    // читалось бы как поломка учётной записи.
    expect(sessionPill({ has_session: true, username: '' }))
      .toEqual({ text: 'Сессия активна', tone: 'ok', title: '' });
  });

  it('без сеанса плашка красная', () => {
    // По ней человек понимает, что бот не поедет, не читая строку ниже.
    expect(sessionPill({ has_session: false, username: '' }))
      .toEqual({ text: 'Нет сессии', tone: 'err', title: '' });
  });
});

describe('слова про сеанс Telegram', () => {
  it('вошедший назван по нику', () => {
    expect(sessionText({ has_session: true, username: 'deadeye' }))
      .toBe('Сессия активна, авторизован как @deadeye');
  });

  it('без ника говорят только про сеанс', () => {
    // Ник спрашивают у самого Telegram, и на холодном старте он не успевает
    // ответить. Пустое «@» выглядело бы поломкой учётной записи.
    expect(sessionText({ has_session: true, username: '' })).toBe('Сессия активна');
  });

  it('без сеанса зовут войти заново', () => {
    // Это единственное, что человек может сделать: без сеанса бот не поедет.
    expect(sessionText({ has_session: false, username: '' }))
      .toBe('Сессии нет — авторизуйтесь заново');
  });
});

describe('шаги входа в Telegram', () => {
  it('код отправлен — ждём код', () => {
    expect(nextStep({ message: 'Код отправлен в Telegram на +7***' })).toBe('code');
  });

  it('на учётной записи двухфакторная защита — просят пароль', () => {
    // Пропусти окно этот шаг, вход завис бы на «Подтвердить» без объяснений.
    expect(nextStep({ need_password: true })).toBe('password');
  });

  it('вход завершён', () => {
    expect(nextStep({ done: true })).toBe('done');
  });
});

describe('подсказка имён моделей', () => {
  const found = ['qwen/qwen3-4b-2507', 'text-embedding-bge-m3', 'llama-3.3-70b'];

  it('поле пусто — виден весь перечень поставщика', () => {
    // Открывший подсказку ещё ничего не набрал, и сузить перечень не по чему:
    // пустой отбор показал бы пустую панель на живом поставщике.
    expect(matchingModels(found, '')).toEqual(found);
  });

  it('набранное сужает перечень и регистра не различает', () => {
    // Имена моделей набирают с середины («bge», «llama»), а не с начала: у
    // локальных они идут с приставкой поставщика через косую черту.
    expect(matchingModels(found, 'QWEN')).toEqual(['qwen/qwen3-4b-2507']);
    expect(matchingModels(found, 'bge')).toEqual(['text-embedding-bge-m3']);
  });

  it('совпавших нет — перечень пуст', () => {
    // Пустая панель здесь и есть ответ: набранного имени у поставщика нет, и
    // подсказывать нечего.
    expect(matchingModels(found, 'gpt-4')).toEqual([]);
  });
});

describe('порог отбора', () => {
  it('перетаскивание меняет показываемое число сразу', () => {
    // Число берётся из того же состояния, что и ползунок: иначе оно отстаёт
    // до перечитывания, и настройку выставляют вслепую.
    expect(thresholdState({ saved: 60 }).drag(75).shown).toBe(75);
  });

  it('до записи сохранённое значение не меняется', () => {
    expect(thresholdState({ saved: 60 }).drag(75).saved).toBe(60);
  });

  it('запись переносит перетащенное в сохранённое', () => {
    expect(thresholdState({ saved: 60 }).drag(75).commit().saved).toBe(75);
  });
});
