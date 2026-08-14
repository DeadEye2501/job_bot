<script>
  // Экран настроек: учётная запись Telegram, оба поставщика моделей, пороги
  // отбора и удаление всех данных.
  //
  // Записывается всё по ходу, без кнопки «сохранить»: поле уезжает на мост,
  // когда его покидают. Так было и в прежнем окне, и это верно для настроек —
  // забытая кнопка означала бы бота, работающего по старому порогу.

  import { call } from '$api/bridge.js';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import LlmSection from '$components/LlmSection.svelte';
  import PipelineSection from '$components/PipelineSection.svelte';
  import SettingsSection from '$components/SettingsSection.svelte';
  import TelegramSection from '$components/TelegramSection.svelte';
  import { credsChanged, idleProbe, loginTrouble, mirrored, probePill, sameCreds } from '$state/settings.js';

  import TelegramLogin from './TelegramLogin.svelte';

  let { ask, say } = $props();

  const WIPE_ASK =
    'Удалить ВСЕ данные приложения?\n\nБудут стёрты база, сессия Telegram, медиафайлы и журнал. Приложение закроется. Откатить нельзя.';

  const LOGOUT_ASK =
    'Выйти из сессии Telegram?\n\nКлюч будет отозван на сервере, бот остановится, а api_id, api_hash и телефон сотрутся из настроек. Войти заново придётся с нуля.';

  let loaded = $state(false);
  let tg = $state(null);
  let draft = $state({ api_id: '', api_hash: '', phone: '' });
  let chat = $state({ base_url: '', api_key: '', model: '' });
  let embed = $state({ base_url: '', api_key: '', model: '' });
  let pipeline = $state({});
  let models = $state({ chat: [], embed: [] });
  let probes = $state({ chat: idleProbe(), embed: idleProbe() });
  let same = $state(false);
  let logging = $state(false);
  let wiping = $state(false);
  let leaving = $state(false);

  const pills = $derived({ chat: probePill(probes.chat), embed: probePill(probes.embed) });

  let alive = true;

  /** Перечитать настройки с моста целиком.
   *
   * Зовётся на входе на экран и после того, что меняет не одно поле: вход в
   * Telegram, выход из него. После обычной записи не зовётся — снимок затёр бы
   * соседнее поле, которое человек правит прямо сейчас.
   */
  async function refresh() {
    const now = await ask('settings.get');
    if (now === null || !alive) return;
    // Плашка проверки говорит про те данные, которые проверяли: приехали
    // другие — ей верить больше нельзя.
    if (credsChanged(chat, now.chat)) probes = { ...probes, chat: idleProbe() };
    if (credsChanged(embed, now.embed)) probes = { ...probes, embed: idleProbe() };
    tg = now.tg;
    chat = now.chat;
    embed = now.embed;
    pipeline = now.pipeline;
    if (!loaded) {
      draft = { api_id: now.tg.api_id, api_hash: now.tg.api_hash, phone: now.tg.phone };
      // Признак выводится из настроек только здесь, при первом чтении: своего
      // поля в базе у него нет. Дальше им распоряжается человек — пересчитывай
      // мы его при каждой записи, снятая галочка возвращалась бы сама, и
      // отдельный адрес для эмбеддингов задать было бы нечем.
      same = sameCreds(now.chat, now.embed);
    }
    loaded = true;
  }

  /** Записать часть настроек.
   *
   * Своё состояние правим сразу, а не по ответу моста: пока ответ идёт,
   * человек успевает уйти из следующего поля, и патч, собранный из прежнего
   * снимка, откатил бы первую правку.
   */
  async function save(patch) {
    await ask('settings.save', patch);
  }

  function saveChat(part) {
    chat = { ...chat, ...part };
    // Перечень имён спрашивается заново на смене адреса или ключа: он с них и
    // читается, и оставленный прежним подсказывал бы модели чужого сервера.
    if (part.model === undefined) listModels('chat');
    // Когда эмбеддинги ходят туда же, их адрес и ключ едут следом: иначе в
    // базе осталась бы пара, которой человек на экране не видел.
    if (!same) return save({ chat });
    embed = mirrored(chat, embed);
    if (part.model === undefined) listModels('embed');
    return save({ chat, embed });
  }

  function saveEmbed(part) {
    embed = { ...embed, ...part };
    if (part.model === undefined) listModels('embed');
    return save({ embed });
  }

  /** Человек переключил «ходить туда же, куда чат».
   *
   * При включении адрес и ключ переезжают от чата; при выключении не меняется
   * ничего — поля просто показываются, и человек вписывает свой адрес сам.
   * Записать в этот миг нечего: прежние значения уже лежат в базе.
   */
  function switchSame(on) {
    same = on;
    if (!on) return;
    embed = mirrored(chat, embed);
    probes = { ...probes, embed: idleProbe() };
    listModels('embed');
    return save({ embed });
  }

  /** Проверить связь с поставщиком.
   *
   * Мосту едут черновые данные из формы, а не сохранённые: человек должен
   * узнать исход до записи — иначе проверять было бы нечего, кроме того, что
   * уже лежит в базе.
   */
  async function probe(kind) {
    const creds = kind === 'chat' ? chat : embed;
    probes = { ...probes, [kind]: { ...idleProbe(), status: 'busy' } };
    let answer = null;
    let trouble = '';
    try {
      // Зовём мост напрямую: отказ поставщика — это и есть исход проверки, и
      // человек читает его в плашке рядом с полем. Общая плашка окна показала
      // бы то же самое и погасла, а искать причину он будет здесь.
      answer = await call('settings.probe_model', { kind, ...creds });
    } catch (refusal) {
      trouble = refusal.message;
    }
    if (!alive) return;
    // Ответ, пришедший после правки полей, отбрасывается: плашка про прежние
    // данные врала бы о нынешних.
    if (probes[kind].status !== 'busy') return;
    if (answer === null) {
      probes = { ...probes, [kind]: { ...idleProbe(), status: 'err', error: trouble } };
      return;
    }
    probes = {
      ...probes,
      [kind]: { status: 'ok', model: answer.model || '', latencyMs: answer.latency_ms || 0, error: '' },
    };
  }

  async function listModels(kind) {
    const creds = kind === 'chat' ? chat : embed;
    const answer = await ask('settings.list_models', {
      kind,
      base_url: creds.base_url,
      api_key: creds.api_key,
    });
    if (answer === null || !alive) return;
    models = { ...models, [kind]: answer.models || [] };
  }

  function startLogin() {
    const trouble = loginTrouble(draft);
    if (trouble) return say(trouble, true);
    logging = true;
  }

  function loggedIn() {
    logging = false;
    say('Вход выполнен');
    return refresh();
  }

  async function logout() {
    leaving = false;
    const done = await ask('settings.logout');
    if (done === null) return;
    await refresh();
  }

  async function wipe() {
    wiping = false;
    say('Удаляем данные…');
    await ask('system.wipe');
  }

  $effect(() => {
    alive = true;
    refresh().then(() => {
      if (alive) {
        listModels('chat');
        listModels('embed');
      }
    });
    return () => {
      alive = false;
    };
  });
</script>

<div class="settings-page">
  <div class="settings-inner">
    {#if !loaded}
      <div class="empty-note">Загрузка…</div>
    {:else}
      <TelegramSection
        {tg}
        {draft}
        onedit={(part) => (draft = { ...draft, ...part })}
        onlogin={startLogin}
        onlogout={() => (leaving = true)}
      />

      <LlmSection
        icon="smart_toy"
        title="LLM для чата"
        creds={chat}
        models={models.chat}
        pill={pills.chat}
        busy={probes.chat.status === 'busy'}
        onsave={saveChat}
        onprobe={() => probe('chat')}
      />

      <LlmSection
        icon="scatter_plot"
        title="LLM для эмбеддингов"
        creds={embed}
        models={models.embed}
        pill={pills.embed}
        busy={probes.embed.status === 'busy'}
        sameAsChat={same}
        onsave={saveEmbed}
        onprobe={() => probe('embed')}
        onsame={switchSame}
      />

      <PipelineSection values={pipeline} onsave={(part) => save({ app: part })} />

      <SettingsSection icon="warning" title="Опасная зона" danger>
        <div class="danger-row">
          <div>
            <div class="danger-text">Удалить все данные</div>
            <div class="danger-sub">
              Полное безвозвратное удаление всех данных приложения: база, сессия Telegram,
              медиафайлы и журнал — а в журнале лежат и куски переписки. Приложение
              закроется, при следующем запуске откроется мастер.
            </div>
          </div>
          <button class="btn danger" type="button" onclick={() => (wiping = true)}>
            <span class="material-symbols-outlined">delete_forever</span>
            Удалить всё
          </button>
        </div>
      </SettingsSection>
    {/if}
  </div>
</div>

{#if logging}
  <TelegramLogin creds={draft} ondone={loggedIn} onclose={() => (logging = false)} />
{/if}

{#if leaving}
  <ConfirmDialog
    message={LOGOUT_ASK}
    confirmLabel="Выйти"
    onconfirm={logout}
    oncancel={() => (leaving = false)}
  />
{/if}

{#if wiping}
  <ConfirmDialog
    message={WIPE_ASK}
    confirmLabel="Удалить всё"
    onconfirm={wipe}
    oncancel={() => (wiping = false)}
  />
{/if}
