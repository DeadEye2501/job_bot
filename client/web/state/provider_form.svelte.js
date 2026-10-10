// Поля поставщика моделей: что в них набрано и что из этого следует.
//
// Своим объявлением, потому что поля одни у шага мастера и у настроек, а
// правила у них общие: что сбрасывается при смене источника, что делает выбор
// файла, как отбивается ответ проверки, пришедший после правки. Написанные
// дважды, они расходятся молча — достаточно в одной копии забыть погасить
// проверку, и «модель отвечает» останется висеть над другой моделью.
//
// Чего здесь нет — того, в чём экраны и расходятся: как показан исход проверки
// (строкой под полями или плашкой в шапке) и когда набранное записывается (по
// «Дальше» или уходом из поля). Это решает сам экран.
//
// От `provider.js` отличается тем, что помнит: там разговор с поставщиком —
// вопрос и ответ, здесь — поля, в которые ответы ложатся.

import { askModels, pickModelFile, probeModel } from './provider.js';
import {
  blankCreds,
  fileCreds,
  fileTrouble,
  idleProbe,
  llmTrouble,
  mirrored,
  presetCreds,
  sourceCreds,
} from './settings.js';

/** Заводит поля поставщика.
 *
 * `kind` — чат или эмбеддинги: с ним спрашивают поставщика. `alive` — признак
 * жизни экрана (`alive.js`): ответ, пришедший после ухода, класть некуда.
 */
export function providerForm({ kind, call, alive }) {
  let creds = $state(blankCreds());
  let models = $state([]);
  let probe = $state(idleProbe());
  // Эмбеддинги из файла модели, а не с сервера.
  let fromFile = $state(false);
  // Эмбеддинги ходят туда же, куда чат, — желание человека, а не факт: файлу
  // и чату на Claude галочка не указ (`sharesChat`).
  let same = $state(false);

  function forget() {
    if (probe.status !== 'idle') probe = idleProbe();
  }

  /** Спросить у поставщика имена его моделей — молча.
   *
   * Перечень — подсказка к полю, а не действие человека: спрашивается он на
   * каждую правку адреса и ключа, и непóднятый поставщик отвечал бы отказом на
   * каждый знак. Отказ не показывается, а отдаётся: по нажатию «Проверить» его
   * читает тот, кто спрашивал.
   */
  async function listModels() {
    const found = await askModels(call, { kind, ...creds });
    if (alive.now) models = found.models;
    return found;
  }

  return {
    /** Набранные адрес, ключ и имя модели. */
    get creds() {
      return creds;
    },
    set creds(value) {
      creds = value;
    },
    /** Имена моделей, которые назвал поставщик, — подсказка к полю имени. */
    get models() {
      return models;
    },
    /** Исход проверки связи: `idleProbe()` с заполненным статусом. */
    get probe() {
      return probe;
    },
    get fromFile() {
      return fromFile;
    },
    /** Что мешает проверить и записать набранное; пусто — ничего. У файла
     *  модели судят файл, у сервера — адрес и имя модели. */
    get trouble() {
      return fromFile ? fileTrouble(creds) : llmTrouble(creds);
    },
    set fromFile(value) {
      fromFile = value;
    },
    get same() {
      return same;
    },
    set same(value) {
      same = value;
    },
    /** Погасить проверку: она говорит про те данные, которые проверяли, и на
     *  поправленных полях лгала бы. */
    forget,
    listModels,
    /** Выбрать готового поставщика: адрес подставляется, имя модели сбрасывается. */
    pickPreset(label) {
      const next = presetCreds(label, creds);
      if (next === null) return;
      creds = next;
      forget();
      return listModels();
    },
    /** Переключить источник эмбеддингов: сервер или файл модели.
     *
     * Набранное для прежнего источника стирается целиком — путь к файлу,
     * дописанный адресом, мост принял бы как сервер. Галочка «как у чата»
     * снимается: у файла чата нет, а вернувшись к серверу, адрес вписывают
     * свой.
     */
    switchSource(toFile) {
      // Выбранный заново тот же источник — не смена: стирать набранное не за что.
      if (toFile === fromFile) return;
      fromFile = toFile;
      creds = sourceCreds(toFile);
      same = false;
      models = [];
      forget();
    },
    /** Спросить файл модели диалогом окна и положить его в поле.
     *
     * Отдаёт ответ диалога: отказ показывает экран, а записывать ли выбранный
     * сразу — тоже решает он. После ухода с экрана отдаётся пустой ответ:
     * ни показывать, ни записывать уже некому.
     */
    async pickFile() {
      const got = await pickModelFile(call);
      if (!alive.now) return { path: '', trouble: '' };
      if (got.path && !got.trouble) {
        creds = fileCreds(got.path);
        forget();
      }
      return got;
    },
    /** Переключить «ходить туда же, куда чат».
     *
     * Включённая галочка переносит адрес и ключ чата; снятая только показывает
     * поля — набранное в них уже чатовое, и человек правит его сам.
     */
    useChat(on, chat) {
      same = on;
      if (!on) return;
      creds = mirrored(chat, creds);
      forget();
      return listModels();
    },
    /** Проверить связь с поставщиком по набранному, а не по записанному.
     *
     * Ответ, пришедший после правки полей, отбрасывается: правка гасит
     * проверку, и исход про прежние данные врал бы о нынешних.
     */
    async verify() {
      probe = { ...idleProbe(), status: 'busy' };
      const done = await probeModel(call, { kind, ...creds });
      if (!alive.now || probe.status !== 'busy') return;
      probe = done.ok
        ? { status: 'ok', model: done.model, latencyMs: done.latencyMs, error: '' }
        : { ...idleProbe(), status: 'err', error: done.trouble };
    },
  };
}
