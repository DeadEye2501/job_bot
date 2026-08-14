// Настройки, переведённые в правила полей и слова состояний.
//
// Чистые функции: ввод и ответы моста приходят доводами, наружу уходят числа,
// строки и признаки. Ни моста, ни разметки этот файл не знает.

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
  return (Math.max(0, Math.min(SCORE_MAX, value)) / SCORE_MAX) * 100;
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

/** Плашка сеанса Telegram в шапке секции.
 *
 * Красная без сеанса: по ней человек понимает, что бот не поедет, не читая
 * строку ниже.
 */
export function sessionPill(tg) {
  if (!tg?.has_session) return { text: 'Нет сессии', tone: 'err', title: '' };
  return { text: tg.username ? `@${tg.username}` : 'Сессия активна', tone: 'ok', title: '' };
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
