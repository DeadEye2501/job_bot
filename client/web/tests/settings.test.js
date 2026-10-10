// Следствия экрана настроек: что человек вводит, что видит и что уезжает на мост.
//
// Предмет — правила полей и слова состояний. Разметка проверяется глазами, а
// вот «во что превратился ввод» и «что показать про сеанс» ломаются молча.

import { describe, expect, it } from 'vitest';

import {
  BOUNDS,
  SOURCE_FILE,
  addressTrouble,
  SOURCE_SERVER,
  addressless,
  isFileSource,
  sharesChat,
  sourceCreds,
  sourceLabel,
  blankCreds,
  canShareChat,
  fileCreds,
  isModelFile,
  mailToSave,
  blankTelegram,
  clampField,
  credsChanged,
  embedReading,
  mirrored,
  nextStep,
  probeLine,
  probePill,
  sameCreds,
  scorePercent,
  sessionPill,
  telegramCreds,
  thresholdState,
} from '../state/settings.js';
import { matching } from '../state/search.js';

import { serverCreds } from './creds.js';

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
  const creds = serverCreds('m');

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
    const chat = serverCreds('chat-model');
    const embed = serverCreds('embed-model');

    expect(sameCreds(chat, embed)).toBe(true);
    expect(sameCreds(chat, { ...embed, base_url: 'http://other' })).toBe(false);
  });

  it('без одной из сторон совпадения нет', () => {
    expect(sameCreds(null, { base_url: '', api_key: '', model: '' })).toBe(false);
  });
});

describe('плашка проверки модели', () => {
  it('удачная проверка называет только время ответа', () => {
    // Модель и так видна в поле под плашкой, а длинное имя — путь к файлу
    // модели — разворачивало плашку в два этажа.
    expect(probePill({ status: 'ok', model: 'qwen', latencyMs: 120 }))
      .toEqual({ text: '120ms', tone: 'ok', title: '' });
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

  it('без нажатия показывает запомненный замер, пока связь жива', () => {
    // Иначе плашки нет, пока не нажали «Проверить», и пропавшая плашка
    // читается как оборванная связь.
    expect(probePill({ status: 'idle' }, 321)).toEqual({ text: '321ms', tone: 'ok', title: '' });
  });

  it('нажатая проверка говорит за себя, а не за прошлый замер', () => {
    expect(probePill({ status: 'busy' }, 321)).toEqual({ text: 'Проверка…', tone: '', title: '' });
  });

  it('непроверенное молчит', () => {
    // Пустая плашка на непроверенном поставщике читалась бы как «что-то не
    // так», хотя не так ровно ничего.
    expect(probePill({ status: 'idle' })).toBe(null);
    expect(probePill({ status: 'idle' }, null)).toBe(null);
  });
});

describe('строка проверки на шаге мастера', () => {
  it('пока проверяют — так и написано', () => {
    expect(probeLine({ status: 'busy' })).toEqual({
      tone: 'busy',
      text: 'Проверяем подключение...',
    });
  });

  it('удача называет модель и время ответа', () => {
    expect(probeLine({ status: 'ok', model: 'qwen', latencyMs: 120 })).toEqual({
      tone: 'ok',
      text: 'Подключение работает (qwen · 120ms)',
    });
  });

  it('отказ поставщика показан его же словами', () => {
    // Строка стоит под полями, места ей хватает: краткое «Ошибка» заставило бы
    // искать причину там, где её нет.
    expect(probeLine({ status: 'err', error: 'Connection refused' })).toEqual({
      tone: 'err',
      text: 'Connection refused',
    });
  });

  it('непроверенное молчит', () => {
    expect(probeLine({ status: 'idle' })).toBe(null);
  });
});

describe('записанные эмбеддинги при первом чтении', () => {
  const chat = serverCreds('chat-model');

  it('путь к файлу модели — источник «файл», с чатом он не делится', () => {
    expect(embedReading(chat, fileCreds('D:/m.gguf'))).toEqual({ fromFile: true, same: false });
  });

  it('тот же адрес и ключ — эмбеддинги ходят туда же, куда чат', () => {
    expect(embedReading(chat, { ...chat, model: 'embed-model' })).toEqual({
      fromFile: false,
      same: true,
    });
  });

  it('свой адрес — свой', () => {
    const embed = { base_url: 'http://other', api_key: 'k', model: 'embed-model' };

    expect(embedReading(chat, embed)).toEqual({ fromFile: false, same: false });
  });

  it('с чатом на Claude не делятся и при совпавших полях', () => {
    // Векторов Claude не считает: взведённая галочка вернулась бы отмеченной
    // вместе с другим поставщиком чата и молча затёрла бы свой сервер.
    const claude = { base_url: 'claude-code', api_key: '', model: 'sonnet' };

    expect(embedReading(claude, { ...claude, model: 'e' }).same).toBe(false);
  });
});

describe('эмбеддинги ходят туда же, куда чат', () => {
  const chat = serverCreds('chat-model');
  const embed = { base_url: 'http://other', api_key: 'иной', model: 'embed-model' };

  it('включили — адрес и ключ переезжают от чата', () => {
    // Без этого в базе осталась бы пара, которой человек на экране уже не
    // видит: поля спрятаны, а разбор вакансий ходит по старому адресу.
    expect(mirrored(chat, embed)).toEqual(serverCreds('embed-model'));
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
    expect(matching(found, '')).toEqual(found);
  });

  it('набранное сужает перечень и регистра не различает', () => {
    // Имена моделей набирают с середины («bge», «llama»), а не с начала: у
    // локальных они идут с приставкой поставщика через косую черту.
    expect(matching(found, 'QWEN')).toEqual(['qwen/qwen3-4b-2507']);
    expect(matching(found, 'bge')).toEqual(['text-embedding-bge-m3']);
  });

  it('совпавших нет — перечень пуст', () => {
    // Пустая панель здесь и есть ответ: набранного имени у поставщика нет, и
    // подсказывать нечего.
    expect(matching(found, 'gpt-4')).toEqual([]);
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

describe('пустые черновики настроек', () => {
  it('пустой вход в Telegram ничем не заполнен', () => {
    // Им экран открывается и к нему же возвращается после выхода из сеанса:
    // останься в полях прежнее, человек отправил бы код на чужой номер.
    expect(blankTelegram()).toEqual({ api_id: '', api_hash: '', phone: '' });
  });

  it('пустые данные поставщика ничем не заполнены', () => {
    expect(blankCreds()).toEqual({ base_url: '', api_key: '', model: '' });
  });

  it('каждый черновик новый', () => {
    // Черновики правят на месте: один на всех протёк бы из настроек в мастер и
    // обратно — и набранный там ключ всплыл бы здесь.
    const creds = blankCreds();
    creds.model = 'qwen';
    const tg = blankTelegram();
    tg.phone = '+70000000000';

    expect(blankCreds().model).toBe('');
    expect(blankTelegram().phone).toBe('');
  });

  it('из ответа моста берутся ровно поля входа', () => {
    // Ответ настроек шире: в нём и признак сеанса, и имя учётной записи, — а в
    // поля идут только те три, которые человек правит.
    expect(
      telegramCreds({ api_id: '12', api_hash: 'ff', phone: '+7', has_session: true, username: 'x' }),
    ).toEqual({ api_id: '12', api_hash: 'ff', phone: '+7' });
  });
});

describe('Claude Code без адреса и ключа', () => {
  it('поля адреса и ключа не нужны только Claude Code', () => {
    // Он ходит под входом человека по подписке: показанные поля просили бы
    // вписать то, чего у него нет.
    expect(addressless('claude-code')).toBe(true);
    expect(addressless('https://api.anthropic.com')).toBe(false);
    expect(addressless('http://localhost:1234')).toBe(false);
  });
});

describe('эмбеддинги «как у чата»', () => {
  it('с чатом на Claude делить адрес нельзя', () => {
    // Claude векторов не считает: эмбеддинги на его адресе бот не примет.
    expect(canShareChat({ base_url: 'https://api.anthropic.com', api_key: 'k', model: 'm' })).toBe(false);
    expect(canShareChat({ base_url: 'claude-code', api_key: '', model: 'sonnet' })).toBe(false);
  });

  it('с OpenAI-совместимым чатом делить можно', () => {
    expect(canShareChat({ base_url: 'https://api.openai.com/v1', api_key: 'k', model: 'm' })).toBe(true);
  });

  it('недописанный адрес проверку не роняет', () => {
    expect(canShareChat({ base_url: 'http://loc', api_key: '', model: '' })).toBe(true);
    expect(canShareChat({ base_url: '', api_key: '', model: '' })).toBe(true);
  });
});

describe('файл модели', () => {
  it('пустой адрес и путь к gguf в любом регистре — файл модели', () => {
    expect(isModelFile({ base_url: '', model: 'd:/models/model.GGUF' })).toBe(true);
  });

  it('адрес сервера — не файл, даже с gguf в имени модели', () => {
    expect(isModelFile({ base_url: 'http://localhost:1234', model: 'model.gguf' })).toBe(false);
  });

  it('пустой черновик — не файл', () => {
    expect(isModelFile(blankCreds())).toBe(false);
  });

  it('выбранный файл ложится в поле модели без адреса и ключа', () => {
    expect(fileCreds('d:/models/model.gguf')).toEqual({
      base_url: '',
      api_key: '',
      model: 'd:/models/model.gguf',
    });
  });
});

describe('эмбеддинги ходят туда же, куда чат', () => {
  const openai = { base_url: 'https://api.openai.com/v1', api_key: 'k', model: 'gpt' };
  const claudeCode = { base_url: 'claude-code', api_key: '', model: 'sonnet' };

  it('только с отмеченной галочкой, сервером и чатом не на Claude', () => {
    expect(sharesChat({ same: true, fromFile: false, chat: openai })).toBe(true);
  });

  it('чат ушёл на Claude — эмбеддинги за ним не едут, хоть галочка и стояла', () => {
    // Иначе адрес Claude ушёл бы в эмбеддинги, а мост такую строку не примет.
    expect(sharesChat({ same: true, fromFile: false, chat: claudeCode })).toBe(false);
  });

  it('эмбеддинги из файла за чатом не едут', () => {
    expect(sharesChat({ same: true, fromFile: true, chat: openai })).toBe(false);
  });
});

describe('источник эмбеддингов', () => {
  it('подпись источника и обратно', () => {
    expect(sourceLabel(true)).toBe(SOURCE_FILE);
    expect(sourceLabel(false)).toBe(SOURCE_SERVER);
    expect(isFileSource(SOURCE_FILE)).toBe(true);
    expect(isFileSource(SOURCE_SERVER)).toBe(false);
  });

  it('смена источника начинает с пустого: путь к файлу не уезжает в сервер', () => {
    // Оставленный путь человек дописал бы адресом, и мост принял бы строку
    // «сервер + путь к .gguf» — бот спрашивал бы у сервера модель по имени пути.
    expect(sourceCreds(false)).toEqual(blankCreds());
    expect(isModelFile(sourceCreds(true))).toBe(false);
    expect(sourceCreds(true).base_url).toBe('');
  });
});

describe('заслон адреса поставщика', () => {
  it('пустой адрес и адрес без схемы не годятся, служебный адрес Claude Code годится', () => {
    // По адресу спрашивают перечень имён ещё до выбора модели: заслон у этого
    // вопроса тот же, что у записи, только без модели.
    expect(addressTrouble('')).toBe('Укажите адрес поставщика');
    expect(addressTrouble('localhost:1234')).toBe('Адрес должен начинаться с http:// или https://');
    expect(addressTrouble('claude-code')).toBe('');
    expect(addressTrouble('http://localhost:1234')).toBe('');
  });
});


describe('запись почты', () => {
  const GMAIL = {
    address: 'me@gmail.com',
    password: 'secret',
    smtp_host: 'smtp.gmail.com',
    smtp_port: 465,
    server_by_address: true,
  };
  const COMPANY = {
    address: 'me@company.test',
    password: 'secret',
    smtp_host: 'smtp.company.test',
    smtp_port: 465,
    server_by_address: false,
  };

  it('сервер, подставленный прежнему адресу, со сменой адреса не уходит', () => {
    expect(mailToSave(GMAIL, { address: ' me@company.test ' })).toEqual({
      address: 'me@company.test',
      password: 'secret',
      smtp_host: null,
      smtp_port: null,
    });
  });

  it('вписанный руками сервер уходит, порт — числом', () => {
    expect(mailToSave(COMPANY, { smtp_port: '587' })).toEqual({
      address: 'me@company.test',
      password: 'secret',
      smtp_host: 'smtp.company.test',
      smtp_port: 587,
    });
    expect(mailToSave(COMPANY, { smtp_host: '  ', smtp_port: 'x' })).toMatchObject({
      smtp_host: null,
      smtp_port: null,
    });
  });

  it('прежний пароль записывать нечего', () => {
    expect(mailToSave(GMAIL, { password: 'secret' })).toBeNull();
    expect(mailToSave(GMAIL, { password: 'other' })).toMatchObject({ password: 'other' });
  });
});
