// Мастер первого запуска: куда он ведёт, что уже пройдено и что не пускает
// дальше.
//
// Чистые функции: пройденное приходит доводом с моста, наружу уходят отметки и
// фразы. Ни моста, ни разметки этот файл не знает.

/** Экраны по порядку. Приветствие и финал — обложки: шага у них нет, и в
 *  строке шагов они ничего не подсвечивают. */
const SCREENS = ['welcome', 'telegram', 'chat', 'embed', 'cv', 'done'];

/** Шаги в строке прогресса. Номер — тот, каким его считает мост
 *  (`wizard.state` отдаёт пройденные номерами). */
const STEPS = [
  { screen: 'telegram', at: 1, label: 'Telegram' },
  { screen: 'chat', at: 2, label: 'Модель' },
  { screen: 'embed', at: 3, label: 'Сравнение' },
  { screen: 'cv', at: 4, label: 'Резюме' },
];

/** Поставщики моделей, чей адрес известен заранее.
 *
 * Адрес подставляется в поле по выбору имени: набирать его руками — первый
 * способ ошибиться в мастере. Первым стоит местный — до него не нужно ничего
 * заводить, и мастер проходится сразу. Адреса, не совпавшего ни с одним из
 * этих, мастер не боится: он и есть «своё».
 */
export const PRESETS = [
  { label: 'LM Studio', base_url: 'http://localhost:1234' },
  { label: 'Ollama', base_url: 'http://localhost:11434' },
  { label: 'OpenAI', base_url: 'https://api.openai.com/v1' },
  { label: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1' },
];

const SCHEME = /^https?:\/\//;

/** Следующий экран мастера или ничего, если это последний. */
export function nextScreen(screen) {
  const at = SCREENS.indexOf(screen);
  return at === SCREENS.length - 1 ? null : SCREENS[at + 1];
}

/** Предыдущий экран или ничего.
 *
 * С финала назад не ведёт: сделанное уже записано, и возвращаться некуда.
 */
export function backScreen(screen) {
  const at = SCREENS.indexOf(screen);
  return at <= 0 || screen === 'done' ? null : SCREENS[at - 1];
}

/** Строка шагов: что пройдено, что проходят сейчас, что впереди.
 *
 * Тот, на котором стоят, подсвечен, даже если пройден: человеку сперва нужно
 * найти себя в строке, а уже потом — сколько осталось. Пройденное считает
 * мост: он смотрит в настройки, а не в то, куда человек нажимал, — и потому
 * переживает закрытое посреди установки окно.
 */
export function stepMarks(completed, screen) {
  return STEPS.map((one) => ({
    label: one.label,
    mark: one.screen === screen ? 'active' : completed.includes(one.at) ? 'done' : '',
  }));
}

/** Что мешает уйти с шага поставщика дальше. Пустая фраза значит «ничего».
 *
 * Мост шлёт запрос по этому адресу как есть: без схемы он не уйдёт никуда, а
 * человек будет думать, что сломалась проверка.
 */
export function llmTrouble(creds) {
  const url = creds.base_url.trim();
  if (!url) return 'Укажите адрес поставщика';
  if (!SCHEME.test(url)) return 'Адрес должен начинаться с http:// или https://';
  if (!creds.model.trim()) return 'Выберите модель';
  return '';
}
