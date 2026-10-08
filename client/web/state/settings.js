// Настройки, переведённые в правила полей и слова состояний.
//
// Чистые функции: ввод и ответы моста приходят доводами, наружу уходят числа,
// строки и признаки. Ни моста, ни разметки этот файл не знает.

import { fillPercent } from './chosen.js';

/** Чем подписано пустое поле имени модели.
 *
 * Пока имён нет, подсказка не обещает списка: перечень читается с адреса и
 * ключа, и у непóднятого поставщика его не будет вовсе — имя тогда вписывают
 * руками. Слова общие на настройки и на шаг мастера: одно и то же поле,
 * подписанное по-разному, читается как два разных.
 */
export function modelPlaceholder(models) {
  return models.length ? 'Модель (выберите из списка или введите свою)' : 'Название модели';
}

/** Чем подписано пустое поле ключа и галочка общих учётных данных.
 *
 * Слова общие на настройки и на шаг мастера: поля там одни и те же, а
 * подписанные по-разному, они читаются как разные. Разъехались они как раз так
 * — «оставьте пустым, если не нужен» против «если требуется».
 */
export const KEY_PLACEHOLDER = 'api_key (оставьте пустым, если не нужен)';
export const SAME_CREDS_LABEL = 'Использовать те же base_url и api_key, что и для чата';

/** Пустой черновик входа в Telegram.
 *
 * Своим объявлением, а не литералом у каждой формы: вход набирают на экране
 * настроек и на шаге мастера, а возвращаются к пустому ещё и после выхода из
 * сеанса. Новый набор полей каждый раз: черновик правят на месте.
 */
export function blankTelegram() {
  return { api_id: '', api_hash: '', phone: '' };
}

/** Поля входа, вынутые из ответа моста.
 *
 * Ответ настроек шире — в нём и признак сеанса, и имя учётной записи, — а в
 * поля идут только эти три, те же, что стоят в пустом черновике. Живут они
 * рядом нарочно: разъедься перечень, форма показывала бы одно, а записывала
 * другое.
 */
export function telegramCreds(tg) {
  return { api_id: tg.api_id, api_hash: tg.api_hash, phone: tg.phone };
}

/** Пустые учётные данные поставщика.
 *
 * Своим объявлением по той же причине: их набирают в настройках — отдельно для
 * чата и для эмбеддингов — и на двух шагах мастера.
 */
export function blankCreds() {
  return { base_url: '', api_key: '', model: '' };
}

/** Пределы длины у полей поставщика.
 *
 * Одни на обе формы: набранное в мастере ложится в то же поле, что и набранное
 * в настройках, и разошедшиеся пределы значат, что принятое одной формой
 * другая уже не примет.
 */
export const CREDS_LIMITS = { base_url: 255, api_key: 512, model: 128 };

/** Предел порога отбора. Дорожка ползунка размечена по нему, и он же
 *  зажимает значение, приехавшее с моста. */
export const SCORE_MAX = 20;

/** Границы числовых полей.
 *
 * Взяты из прежнего окна и держатся окном же: у моста верхних границ нет
 * вовсе, а нижние — это `minimum` его разбора. То есть числа тут наши, а не
 * пересказ чужих, и придуманы они по делу: сутки — потолок осмысленного
 * интервала опроса, пять сотен — потолок того, что бот успевает разобрать за
 * цикл.
 */
export const BOUNDS = {
  poll_interval_sec: { min: 10, max: 86400 },
  backfill_limit: { min: 1, max: 500 },
  dm_backfill_limit: { min: 1, max: 500 },
};

/** Во что превратился ввод числового поля.
 *
 * Границы стоят у бэкенда, и окно их держит заранее: пропусти оно ноль секунд
 * опроса, бот пошёл бы в Telegram без передышки. За границей значение
 * прижимается к ней, а негодный ввод — пустое поле, буквы, знак — откатывается
 * к прежнему сохранённому: опечатку нельзя принимать за ноль, иначе человек
 * молча получит настройку, которой не задавал.
 */
export function clampField(raw, { min, max, fallback }) {
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

/** Какую долю дорожки залить под этот порог. */
export function scorePercent(value) {
  return fillPercent(value, SCORE_MAX);
}

/** Порог в двух видах: что человек тянет и что уже записано.
 *
 * Показываемое число и заливка берутся из перетаскиваемого, а не из
 * записанного: запись уходит на мосту по отпусканию, и до его ответа число
 * рядом с ползунком отставало бы — порог выставляли бы вслепую. Записанное
 * остаётся прежним до самой записи: по нему видно, что именно сейчас держит
 * бот.
 */
export function thresholdState({ saved, shown = saved }) {
  return {
    saved,
    shown,
    drag: (value) => thresholdState({ saved, shown: value }),
    commit: () => thresholdState({ saved: shown }),
  };
}

/** Сменились ли учётные данные поставщика.
 *
 * По этому ответу гасится плашка проверки: она говорит «модель отвечает» про
 * тот адрес и ту модель, которые проверяли, и на изменённых полях лгала бы.
 */
export function credsChanged(before, after) {
  if (!before || !after) return before !== after;
  return (
    before.base_url !== after.base_url ||
    before.api_key !== after.api_key ||
    before.model !== after.model
  );
}

/** Ходят ли эмбеддинги туда же, куда чат.
 *
 * Модель в сравнение не входит: у эмбеддингов она своя всегда и совпасть с
 * чатовой не может.
 */
export function sameCreds(chat, embed) {
  if (!chat || !embed) return false;
  return chat.base_url === embed.base_url && chat.api_key === embed.api_key;
}

/** Учётные данные эмбеддингов, когда они ходят туда же, куда чат.
 *
 * Модель остаётся своей: чатовая модель векторов не считает, и подставь её —
 * первый же разбор вакансии вернул бы мусор вместо вектора.
 */
export function mirrored(chat, embed) {
  return { base_url: chat.base_url, api_key: chat.api_key, model: embed.model };
}

/** Служебный адрес Claude Code — тот же, что ждёт мост: сервера у него нет. */
const CLAUDE_CODE_ADDRESS = 'claude-code';
const CLAUDE_HOST = 'api.anthropic.com';

/** Поставщики моделей, чей адрес известен заранее.
 *
 * Адрес подставляется в поле по выбору имени: набирать его руками — первый
 * способ ошибиться. Список один на мастер и настройки: выбранное в одном месте
 * узнаётся в другом. Адреса, не совпавшего ни с одним из этих, бояться нечего:
 * он и есть «своё».
 */
export const PRESETS = [
  { label: 'OpenAI', base_url: 'https://api.openai.com/v1' },
  { label: 'Anthropic', base_url: `https://${CLAUDE_HOST}` },
  { label: 'Claude Code', base_url: CLAUDE_CODE_ADDRESS },
  { label: 'LM Studio', base_url: 'http://localhost:1234' },
  { label: 'Ollama', base_url: 'http://localhost:11434' },
  { label: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1' },
  { label: 'Custom', base_url: '' },
];

/** Имена поставщиков — то, из чего выбирают в списке. */
export const PRESET_NAMES = PRESETS.map((one) => one.label);

/** Каким поставщиком отмечен этот адрес.
 *
 * Незнакомый — «своё»: без такого пункта набранный руками адрес оставлял бы
 * выбор пустым, и человек читал бы это как «поставщик не выбран», хотя адрес
 * у него уже вписан.
 */
export function presetFor(url) {
  const typed = url.trim();
  return PRESETS.find((one) => one.base_url && one.base_url === typed)?.label ?? 'Custom';
}

/** Учётные данные поставщика, выбранного по имени; имя модели сбрасывается.
 *
 * Набранное для прежнего поставщика у нового почти наверняка не заведётся, и
 * оставленное имя ушло бы в проверку молчаливой ошибкой. Незнакомое имя — ничего.
 */
export function presetCreds(label, creds) {
  const preset = PRESETS.find((one) => one.label === label);
  return preset === undefined ? null : { ...creds, base_url: preset.base_url, model: '' };
}

/** Нужны ли поставщику адрес и ключ: Claude Code ходит под входом человека. */
export function addressless(url) {
  return url.trim() === CLAUDE_CODE_ADDRESS;
}

/** Ведёт ли адрес к Claude — по API или через Claude Code.
 *
 * Недописанный адрес — не беда: его набирают по знаку, и проверка на каждом
 * знаке не должна падать.
 */
function servesClaude(url) {
  if (addressless(url)) return true;
  try {
    return new URL(url).hostname === CLAUDE_HOST;
  } catch {
    return false;
  }
}

/** Можно ли эмбеддингам ходить туда же, куда чат.
 *
 * Claude векторов не считает: эмбеддинги на его адресе мост не примет, и
 * галочка «как у чата» предлагала бы то, что не заработает.
 */
export function canShareChat(chat) {
  return !servesClaude(chat.base_url);
}

/** Откуда берутся эмбеддинги: с сервера или из файла модели на диске. */
export const SOURCE_SERVER = 'Сервер';
export const SOURCE_FILE = 'Файл';
export const EMBED_SOURCES = [SOURCE_SERVER, SOURCE_FILE];

/** Подпись источника эмбеддингов по признаку «из файла». */
export function sourceLabel(fromFile) {
  return fromFile ? SOURCE_FILE : SOURCE_SERVER;
}

/** Из файла ли источник, выбранный по подписи. */
export function isFileSource(label) {
  return label === SOURCE_FILE;
}

/** Черновик эмбеддингов на смене источника — пустой.
 *
 * Прежнее с другого источника не годится: путь к файлу, дописанный адресом,
 * мост принял бы как сервер с моделью по имени пути.
 */
export function sourceCreds(toFile) {
  return toFile ? fileCreds('') : blankCreds();
}

/** Ходят ли эмбеддинги туда же, куда чат, прямо сейчас.
 *
 * Галочка — лишь желание человека: эмбеддинги из файла и чат на Claude ей не
 * подчиняются. Векторов Claude не считает, и адрес чата, уехавший в
 * эмбеддинги, мост бы не принял.
 */
export function sharesChat({ same, fromFile, chat }) {
  return same && !fromFile && canShareChat(chat);
}

/** Чем подписано пустое поле пути к файлу модели. */
export const NO_FILE_PLACEHOLDER = 'Файл модели не выбран';

const SCHEME = /^https?:\/\//;


/** Указывают ли учётные данные на файл модели — тем же признаком, что у моста:
 *  адреса нет, в поле модели путь к `.gguf` в любом регистре. */
export function isModelFile(creds) {
  return !creds.base_url && /\.gguf$/i.test(creds.model || '');
}

/** Учётные данные эмбеддингов из выбранного файла модели. */
export function fileCreds(path) {
  return { base_url: '', api_key: '', model: path };
}


/** Плашка сеанса Telegram в шапке секции.
 *
 * Красная без сеанса: по ней человек понимает, что бот не поедет, не читая
 * строку ниже.
 */
export function sessionPill(tg) {
  if (!tg?.has_session) return { text: 'Нет сессии', tone: 'err', title: '' };
  return { text: tg.username ? `@${tg.username}` : 'Сессия активна', tone: 'ok', title: '' };
}

/** Проверка, которой ещё не было.
 *
 * Одним объявлением на оба экрана и на оба места — начальное состояние и сброс
 * после правки полей: разъедься они, плашка проверки пережила бы данные, о
 * которых говорит.
 */
export function idleProbe() {
  return { status: 'idle', model: '', latencyMs: 0, error: '' };
}

/** Чего не хватает, чтобы начать вход в Telegram. Пустая фраза значит «ничего».
 *
 * Проверяется здесь, а не отказом моста: пустое поле — это забывчивость, и
 * сказать про неё надо словом, которое называет забытое.
 */
export function loginTrouble(draft) {
  if (draft.api_id && draft.api_hash && draft.phone) return '';
  return 'Заполните api_id, api_hash и телефон';
}

/** Что показать в плашке проверки поставщика — или ничего.
 *
 * Беда показывается коротким словом, а ответ провайдера уезжает в подсказку:
 * он бывает на десять строк и развалил бы полосу заголовка. Непроверенное
 * молчит: пустая плашка читалась бы как «что-то не так».
 */
export function probePill(probe) {
  if (probe.status === 'ok') {
    return { text: `${probe.model} · ${probe.latencyMs}ms`, tone: 'ok', title: '' };
  }
  if (probe.status === 'err') {
    return { text: 'Ошибка', tone: 'err', title: probe.error };
  }
  if (probe.status === 'busy') {
    return { text: 'Проверка…', tone: '', title: '' };
  }
  return null;
}

/** Что сказать человеку про сеанс Telegram.
 *
 * Ник спрашивают у самого Telegram, и на холодном старте он не успевает
 * ответить: пустое «@» выглядело бы поломкой учётной записи, поэтому без ника
 * говорят только про сеанс.
 */
export function sessionText(tg) {
  if (!tg?.has_session) return 'Сессии нет — авторизуйтесь заново';
  return tg.username ? `Сессия активна, авторизован как @${tg.username}` : 'Сессия активна';
}

/** На каком шаге вход после ответа моста.
 *
 * Шага три, и мост называет только достигнутое: код отправлен, спрошен
 * облачный пароль, вход завершён.
 */
export function nextStep(answer) {
  if (answer.done) return 'done';
  return answer.need_password ? 'password' : 'code';
}

/** Что мешает уйти с шага поставщика дальше. Пустая фраза значит «ничего».
 *
 * Мост шлёт запрос по этому адресу как есть: без схемы он не уйдёт никуда, а
 * человек будет думать, что сломалась проверка. У Claude Code сервера нет —
 * вместо адреса служебное слово, и по схеме его не судят.
 */
export function llmTrouble(creds) {
  const url = creds.base_url.trim();
  if (!url) return 'Укажите адрес поставщика';
  if (!addressless(url) && !SCHEME.test(url)) {
    return 'Адрес должен начинаться с http:// или https://';
  }
  if (!creds.model.trim()) return 'Выберите модель';
  return '';
}

/** Что мешает уйти с шага эмбеддингов из файла. Пустая фраза значит «ничего». */
export function fileTrouble(creds) {
  return isModelFile(creds) ? '' : 'Выберите файл модели';
}
