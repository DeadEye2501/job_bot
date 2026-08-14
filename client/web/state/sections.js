// Разделы окна: перечень пунктов бокового меню.

/** Разделы в том порядке, в каком они стоят в меню. Значок — лигатура шрифта
 *  `Material Symbols Outlined`. */
export const SECTIONS = [
  { key: 'profile', label: 'Профиль', icon: 'account_circle' },
  { key: 'vacancies', label: 'Вакансии', icon: 'list_alt' },
  { key: 'contacts', label: 'Контакты', icon: 'people' },
  { key: 'stats', label: 'Статистика', icon: 'bar_chart' },
  { key: 'system', label: 'Система', icon: 'settings' },
];

/** Вкладки раздела «Система» в том порядке, в каком они стояли в прежнем окне.
 *  Настройки идут первыми и открыты по умолчанию — так было и там. */
export const SYSTEM_TABS = [
  { key: 'settings', label: 'Настройки' },
  { key: 'logs', label: 'Логи' },
];

/** Вкладки раздела «Профиль». Подписи английские — так они и стояли. */
export const PROFILE_TABS = [
  { key: 'cv', label: 'CV' },
  { key: 'skills', label: 'Skills' },
  { key: 'experience', label: 'Experience' },
];

/** Вкладки раздела «Контакты». Каналы первыми — с них начинается сбор. */
export const CONTACTS_TABS = [
  { key: 'channels', label: 'Каналы' },
  { key: 'companies', label: 'Компании' },
  { key: 'people', label: 'HR' },
  { key: 'blacklist', label: 'Чёрный список' },
];
