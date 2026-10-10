// Действия над вакансией: что из них сейчас запрещено и чем это объясняется.
//
// Чистые функции: карточка приходит доводом, наружу уходят фразы. Ни моста, ни
// разметки этот файл не знает.

import { showStamp } from './dates.js';
import { RUNNING } from './round.svelte.js';
import { handleName } from './telegram.js';
import { plural } from './words.js';

/** Почему отклик и переразбор сейчас недоступны.
 *
 * Пустая фраза значит «доступно». Обе просьбы уходят боту, поэтому неживое
 * окружение запирает оба и объясняется теми же словами, что и кнопка обхода
 * внизу окна: две разные фразы об одной беде человек читает как две беды.
 *
 * Идущий обход запирает оба: прогон сам зовёт модель, а параллельной работы
 * модели не допускаем — даже отклика в Telegram, которому браузер не нужен.
 *
 * Есть ли куда откликаться, здесь не решается: это знает только мост, и
 * ответ его разбирает `applyChoices`.
 */
export function actionBlocks(card, lockedTip, running) {
  const busy = lockedTip || (running ? RUNNING : '');
  return {
    send: busy,
    // Пустой текст разбор не запирает: его зовут как раз тогда, когда карточка
    // вышла кривой, и заслон отнял бы единственный способ это поправить.
    rerun: busy,
    // Переход к посту наружу ходит мимо бота, поэтому неживое окружение его не
    // касается: заперт он только тем, что ссылки может не быть вовсе.
    source: card.source_url ? '' : 'Нет ссылки на источник',
    // Исходника не бывает у заведённой полями: описание к ней пишет человек, а
    // не автор объявления. Окно, открытое над пустотой, читается как поломка —
    // одни подписи и ни строки текста.
    raw: card.raw_text ? '' : 'У вакансии нет исходного текста',
  };
}

/** Способы отклика строками окна выбора: Telegram первым, за ним способы агента.
 *
 * Строка — один контакт: ник Telegram с собакой, по которой его и узнают, или
 * адрес — ссылка на сайт, почта.
 *
 * Довод — ответ `vacancies.apply_ways`. Telegram шлёт бот прежней отправкой,
 * поэтому `way` у него пустой; у способа агента это то, что мост ждёт обратно в
 * `vacancies.apply_via`. Запертому агенту работать нечем, и его способы в окно
 * не попадают.
 */
export function applyChoices(found, hr) {
  const viaTelegram = found.telegram
    ? [{ key: 'telegram', contact: telegramName(hr), way: null }]
    : [];
  const viaAgent = found.lock
    ? []
    : found.ways.map((way) => ({ key: `${way.method} ${way.target}`, contact: way.target, way }));
  return [...viaTelegram, ...viaAgent];
}

/** Почему откликнуться некуда: способы есть, но агент заперт, — или их нет вовсе. */
export function noChoiceReason(found) {
  return found.ways.length && found.lock
    ? found.lock
    : 'Откликнуться некуда: нет ни HR, ни контактов для отклика';
}

function telegramName(hr) {
  return hr?.telegram_username ? handleName(hr.telegram_username) : hr?.name || '—';
}

/** Пилюля источника в шапке карточки: откуда вакансия и куда ведёт нажатие.
 *
 * Канал и агрегатор показаны одинаково — источник у вакансии один, и пилюля
 * его заполняется сама, по привязке. Ведёт она по `source_url`: у вакансии из
 * канала это пост, у вакансии с агрегатора или из сети — её страница на сайте.
 * Без источника пилюли нет: пустая читалась бы как потерянный источник.
 */
export function sourcePill(card) {
  if (card.channel_username) {
    return { icon: 'tag', text: card.channel_username, title: 'Перейти к посту в канале' };
  }
  if (card.aggregator_name) {
    return { icon: 'language', text: siteName(card), title: 'Перейти к вакансии на сайте' };
  }
  return null;
}

/** Имя сайта-источника. У найденной поиском по сети — «Сайт»: «Поиск по сети»
 *  — способ, которым её нашли, а не место, откуда она пришла. */
function siteName(card) {
  return card.from_web_search ? 'Сайт' : card.aggregator_name;
}

/** Чем подписан исходный текст объявления — чипами над самим текстом.
 *
 * По каналу, номеру сообщения и времени поста объявление находят в самом
 * Telegram, когда разбор вышел кривым; длина говорит, весь ли пост дошёл.
 * Пропавшие чипы не оставляют пустых мест: канал могли снести, а номер и метка
 * времени приходят не от всякого источника.
 */
export function rawChips(card) {
  const length = (card.raw_text || '').length;
  // Когда объявление вышло: у поста своя метка, у записи — только время
  // заведения, и второе на день-другой позже первого.
  const stamp = showStamp(card.posted_at || card.created_at);
  const chips = [
    card.channel_username ? { icon: 'tag', text: `@${card.channel_username}` } : null,
    card.aggregator_name ? { icon: 'language', text: siteName(card) } : null,
    card.source_msg_id === null || card.source_msg_id === undefined
      ? null
      : { icon: 'numbers', text: `msg #${card.source_msg_id}` },
    stamp ? { icon: 'schedule', text: stamp } : null,
    { icon: 'straighten', text: `${length} ${plural(length, 'символ', 'символа', 'символов')}` },
  ];
  return chips.filter(Boolean);
}
