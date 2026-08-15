// Следствия мастера: куда он ведёт, что помечает пройденным и что не пускает
// дальше.

import { describe, expect, it } from 'vitest';

import {
  PRESETS, backScreen, cvModes, cvReady, llmTrouble, nextScreen, presetFor, stepMarks,
} from '../state/wizard.js';

describe('ход мастера', () => {
  it('ведёт от приветствия к шагам и к финалу', () => {
    // Порядок несущий: до модели нельзя добраться, не заведя учётную запись, —
    // без неё боту нечего разбирать.
    const path = [];
    let screen = 'welcome';
    while (screen !== null) {
      path.push(screen);
      screen = nextScreen(screen);
    }
    expect(path).toEqual(['welcome', 'telegram', 'chat', 'embed', 'cv', 'done']);
  });

  it('с финала дальше не ведёт никуда', () => {
    // Дальше — само приложение, и уводит туда отдельная кнопка, а не шаг.
    expect(nextScreen('done')).toBe(null);
  });

  it('назад ведёт по тому же пути, а с приветствия — никуда', () => {
    expect(backScreen('chat')).toBe('telegram');
    expect(backScreen('welcome')).toBe(null);
  });

  it('с финала назад не ведёт: сделанное уже записано', () => {
    expect(backScreen('done')).toBe(null);
  });
});

describe('отметки шагов', () => {
  it('пройденное отмечено, нынешнее подсвечено, остальное пусто', () => {
    // По этой строке человек понимает, сколько ещё осталось; ошибись она —
    // мастер выглядел бы бесконечным.
    expect(stepMarks([1], 'chat').map((one) => one.mark)).toEqual(['done', 'active', '', '']);
  });

  it('на обложках не подсвечен ни один шаг', () => {
    // Приветствие и финал не шаги: подсвеченный первый обещал бы, что его уже
    // проходят.
    expect(stepMarks([], 'welcome').map((one) => one.mark)).toEqual(['', '', '', '']);
    // И у вернувшегося тоже: на обложке строка шагов показывает цифры, а не
    // галочки, — иначе приглушённые отметки читаются как недоступные шаги.
    expect(stepMarks([1, 2], 'welcome').map((one) => one.mark)).toEqual(['', '', '', '']);
    expect(stepMarks([1, 2, 3, 4], 'done').map((one) => one.mark)).toEqual([
      'done',
      'done',
      'done',
      'done',
    ]);
  });

  it('шаг, на который вернулись, подсвечен, а не отмечен пройденным', () => {
    // Человеку сперва нужно найти себя в строке шагов: отметка о пройденном
    // здесь сказала бы «ты не здесь», хотя он именно здесь.
    expect(stepMarks([1, 2], 'telegram').map((one) => one.mark)).toEqual([
      'active',
      'done',
      '',
      '',
    ]);
  });
});

describe('заслон перед моделью', () => {
  it('без адреса дальше не пускают', () => {
    expect(llmTrouble({ base_url: '', model: 'gpt' })).toBe('Укажите адрес поставщика');
  });

  it('адрес без схемы не годится', () => {
    // Мост шлёт запрос как есть; без `http://` он не уйдёт никуда, а человек
    // будет думать, что проверка сломалась.
    expect(llmTrouble({ base_url: 'localhost:1234', model: 'gpt' })).toBe(
      'Адрес должен начинаться с http:// или https://',
    );
  });

  it('без имени модели дальше не пускают', () => {
    expect(llmTrouble({ base_url: 'http://localhost:1234', model: '  ' })).toBe('Выберите модель');
  });

  it('заполненное пропускают', () => {
    expect(llmTrouble({ base_url: 'https://api.openai.com/v1', model: 'gpt-4o' })).toBe('');
  });
});

describe('готовые поставщики', () => {
  it('адрес каждого проходит заслон сразу, без правки руками', () => {
    // Затем они и выписаны: подставленный адрес не должен требовать от
    // человека дописывать схему. Пустой перечень такой проверки не переживёт —
    // подставлять было бы нечего.
    const ready = PRESETS.filter((one) => one.base_url);
    expect(ready.length).toBeGreaterThan(0);
    const troubles = ready.map((one) => llmTrouble({ base_url: one.base_url, model: 'x' }));
    expect(troubles).toEqual(ready.map(() => ''));
  });

  it('знакомый адрес отмечает своего поставщика', () => {
    // По отметке человек узнаёт, куда он ходит: подставленный адрес и выбранное
    // имя обязаны совпадать, иначе выбор читается как несделанный.
    expect(presetFor('http://localhost:1234')).toBe('LM Studio');
  });

  it('незнакомый адрес отмечен как свой, а не как ничей', () => {
    // Своё в перечне есть нарочно: без него набранный руками адрес оставлял бы
    // выбор пустым, и человек думал бы, что поставщик не выбран.
    expect(presetFor('https://my-own-llm.example/v1')).toBe('Custom');
    expect(presetFor('')).toBe('Custom');
  });

  it('адрес с лишними пробелами по краям заслон пропускает', () => {
    // Адрес набирают вставкой из чужого окна, и пробел на конце приезжает
    // вместе с ним; заслон судит по обрезанному, и уезжает на мост тоже
    // обрезанный.
    expect(llmTrouble({ base_url: '  http://localhost:1234  ', model: 'x' })).toBe('');
  });
});

describe('шаг резюме', () => {
  it('без файла «Готово» заперто, пока не выбран «Пропустить шаг»', () => {
    // Иначе мастер отправляет пустой путь, и шаг завершается ничем.
    expect(cvReady({ mode: 'attach', path: '' })).toBe(false);
  });

  it('«Пропустить шаг» отпирает «Готово» и без файла', () => {
    expect(cvReady({ mode: 'skip', path: '' })).toBe(true);
  });

  it('с выбранным файлом «Готово» отперто', () => {
    expect(cvReady({ mode: 'attach', path: 'C:/cv.pdf' })).toBe(true);
  });

  it('режим «Разобрать через LLM» выбрать нельзя', () => {
    // В образце карточка заперта: разбор ещё не написан, и выбор режима завёл
    // бы мастер в шаг, который ничего не делает.
    expect(cvModes().find((mode) => mode.id === 'parse').disabled).toBe(true);
  });
});
