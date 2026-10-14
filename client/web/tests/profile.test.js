// Следствия экрана профиля: что человек читает про файл резюме и анкету.
//
// Предмет — слова и числа, которые видны на экране, и сборка того, что уезжает
// на мост. Разметка проверяется глазами.

import { describe, expect, it } from 'vitest';

import {
  blankProfile,
  cvNote,
  cvOpenable,
  fileSize,
  langRow,
  named,
  profileSheet,
  updatedNote,
} from '../state/profile.js';

describe('анкета, уезжающая на мост', () => {
  it('сумма с пробелами между разрядами уезжает числом', () => {
    // «150 000» человек пишет так, как привык читать, а мост считает суммой
    // только цифры: с пробелом она легла бы пустотой.
    const form = { ...blankProfile(), expected_salary: '150 000' };
    expect(profileSheet(form, new Set(), new Set()).expected_salary).toBe('150000');
  });

  it('неразрывный пробел между разрядами — тоже не часть суммы', () => {
    // Скопированная из чужого текста сумма приходит с неразрывными пробелами.
    const form = { ...blankProfile(), expected_salary: '150 000' };
    expect(profileSheet(form, new Set(), new Set()).expected_salary).toBe('150000');
  });

  it('грейды и форматы уезжают списками', () => {
    const sheet = profileSheet(blankProfile(), new Set(['Senior']), new Set(['remote']));
    expect(sheet.grades).toEqual(['Senior']);
    expect(sheet.work_format).toEqual(['remote']);
  });
});

describe('размер файла резюме', () => {
  it('малое показано в байтах', () => {
    // Пустой или почти пустой файл — признак сорвавшейся замены, и «0 КБ»
    // читалось бы как «всё в порядке».
    expect(fileSize(512)).toBe('512 Б');
  });

  it('обычное резюме — в килобайтах без дробей', () => {
    // Доли килобайта человеку ничего не говорят, а место в строке занимают.
    expect(fileSize(120 * 1024)).toBe('120 КБ');
  });

  it('крупное — в мегабайтах с одним знаком', () => {
    // Здесь дробь уже значима: 1.2 и 1.9 МБ — разные файлы.
    expect(fileSize(1.25 * 1024 * 1024)).toBe('1.3 МБ');
  });
});

describe('строка про файл резюме', () => {
  it('открыть можно только файл, который есть на диске', () => {
    expect(cvOpenable(null)).toBe(false);
    expect(cvOpenable({ name: 'cv.pdf', size: 1, exists: false })).toBe(false);
    expect(cvOpenable({ name: 'cv.pdf', size: 1, exists: true })).toBe(true);
  });

  it('без файла так и сказано', () => {
    // Пустое место читалось бы как «файл есть, но имя не показали».
    expect(cvNote(null)).toEqual({ name: 'Файл не выбран', note: '' });
  });

  it('файл на месте — имя и размер', () => {
    expect(cvNote({ name: 'cv.pdf', size: 2048, exists: true }))
      .toEqual({ name: 'cv.pdf', note: '2 КБ' });
  });

  it('файл прописан, но исчез с диска — сказано прямо', () => {
    // Это главный случай: путь в настройках есть, бот прикладывает резюме к
    // отклику, а файла нет. Молчи об этом экран — человек узнал бы от HR.
    expect(cvNote({ name: 'cv.pdf', size: 2048, exists: false }))
      .toEqual({ name: 'cv.pdf', note: '2 КБ · файл не найден' });
  });
});

describe('отметка о правке анкеты', () => {
  it('неправленая анкета отмечена прочерком', () => {
    expect(updatedNote(null)).toBe('—');
  });

  it('правленая называет день и время', () => {
    // По ним человек понимает, что запись дошла: кнопки «сохранить» на этом
    // экране нет вовсе, и другого подтверждения он не получает.
    expect(updatedNote(new Date(2026, 7, 14, 9, 5).toISOString()))
      .toBe('обновлено 2026-08-14 09:05');
  });

  it('негодная метка отмечена прочерком, а не буквами NaN', () => {
    // Метка приходит с моста, и порченая запись в базе не должна выглядеть
    // сообщением о времени: «обновлено NaN-NaN-NaN NaN:NaN» читается как
    // поломка окна, а не как отсутствие даты.
    expect(updatedNote('позавчера')).toBe('—');
  });
});

describe('что уезжает на мост', () => {
  it('безымянные строки не отправляются', () => {
    // Свежая строка рождается пустой, и человек в этот миг ещё набирает имя;
    // мост такую не примет и откажет всей записи разом.
    const rows = [{ name: 'Python' }, { name: '   ' }, { name: '' }];

    expect(named(rows, 'name')).toEqual([{ name: 'Python' }]);
  });

  it('отбор одинаков для навыков и мест работы', () => {
    // Правило одно, а полей два: у навыка имя, у места работы название
    // компании. Разойдись они — на одной вкладке пустое уезжало бы, на другой
    // нет, и отказ моста выглядел бы случайным.
    expect(named([{ company: 'Контур' }, { company: '' }], 'company'))
      .toEqual([{ company: 'Контур' }]);
  });

  it('пустая анкета — это все поля, а не половина', () => {
    // Мост принимает анкету целиком: пропущенное поле уедет как `undefined` и
    // сотрёт то, что в базе уже лежало. Поэтому сверяется вся нагрузка разом,
    // а не четыре поля вразбивку: выпади из неё образование — человек терял
    // бы его на первом же сохранении, а четыре названных поля были бы целы.
    expect(blankProfile()).toEqual({
      first_name: '',
      last_name: '',
      first_name_latin: '',
      last_name_latin: '',
      patronymic: '',
      patronymic_latin: '',
      birth_date: '',
      citizenship: '',
      gender: '',
      title: '',
      email: '',
      phone: '',
      telegram_username: '',
      github_url: '',
      location: '',
      education: '',
      about_me: '',
      free_preferences: '',
      resume_url: '',
      expected_salary: '',
      expected_salary_currency: '',
      expected_salary_period: '',
      grades: [],
      work_format: [],
      languages: [],
      updated_at: null,
    });
  });
});

describe('строка языка', () => {
  it('новая строка пустая и со средним уровнем', () => {
    // Пустой уровень мост не примет, а «native» по умолчанию соврал бы за
    // человека в анкете, которую читает HR.
    expect(langRow()).toEqual({ language: '', level: 'B2' });
  });

});
