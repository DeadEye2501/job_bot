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
  import { living } from '$state/alive.js';
  import { askModels, probeModel } from '$state/provider.js';
  import { credsChanged, idleProbe, loginTrouble, mirrored, probePill, sameCreds } from '$state/settings.js';

  import TelegramLogin from './TelegramLogin.svelte';

  let { ask, say } = $props();

  const WIPE_ASK =
    'Удалить ВСЕ данные приложения?\n\nБудут стёрты база, сессия Telegram, медиафайлы и журнал. Приложение закроется. Откатить нельзя.';

  const LOGOUT_ASK =
    'Выйти из сессии Telegram?\n\nКлюч будет отозван на сервере, бот остановится, а api_id, api_hash и телефон сотрутся из настроек. Войти заново придётся с нуля.';

  // Пустой черновик входа: им экран открывается и к нему же возвращается после
  // выхода из сессии.
  const BLANK_TG = { api_id: '', api_hash: '', phone: '' };

  let loaded = $state(false);
  let tg = $state(null);
  let draft = $state({ ...BLANK_TG });
  let chat = $state({ base_url: '', api_key: '', model: '' });
  let embed = $state({ base_url: '', api_key: '', model: '' });
  let pipeline = $state({});
  let models = $state({ chat: [], embed: [] });
  let probes = $state({ chat: idleProbe(), embed: idleProbe() });
  let same = $state(false);
  let logging = $state(false);
  let wiping = $state(false);
  let leaving = $state(false);
  // Кнопки, отпустить которые до ответа нельзя: обе делают необратимое, и
  // второе нажатие ушло бы в уже начатую работу.
  let leavingBusy = $state(false);
  let wipingBusy = $state(false);

  const pills = $derived({ chat: probePill(probes.chat), embed: probePill(probes.embed) });

  const alive = living();

  /** Перечитать настройки с моста целиком.
   *
   * Зовётся на входе на экран и после того, что меняет не одно поле: вход в
   * Telegram, выход из него. После обычной записи не зовётся — снимок затёр бы
   * соседнее поле, которое человек правит прямо сейчас.
   */
  async function refresh() {
    const now = await ask('settings.get');
    if (now === null || !alive.now) return;
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

  /** Записать поле пайплайна, оставив записанное у себя.
   *
   * Своё состояние правится сразу: по нему откатывается негодный ввод соседнего
   * поля — а откат к тому, что приехало при открытии экрана, вернул бы число,
   * которое человек уже сменил.
   */
  function savePipeline(part) {
    pipeline = { ...pipeline, ...part };
    return save({ app: part });
  }

  /** Человек правит поля поставщика — плашка проверки больше не про них. */
  function forgetProbe(kind) {
    if (probes[kind].status === 'idle') return;
    probes = { ...probes, [kind]: idleProbe() };
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
    // Пустую форму не отправляем: поставщик ответит отказом про разбор адреса,
    // и человек будет искать беду в сети вместо незаполненного поля.
    if (!creds.base_url || !creds.model) return say('Заполните base_url и модель', true);
    probes = { ...probes, [kind]: { ...idleProbe(), status: 'busy' } };
    const done = await probeModel(call, { kind, ...creds });
    if (!alive.now) return;
    // Ответ, пришедший после правки полей, отбрасывается: плашка про прежние
    // данные врала бы о нынешних.
    if (probes[kind].status !== 'busy') return;
    if (!done.ok) {
      probes = { ...probes, [kind]: { ...idleProbe(), status: 'err', error: done.trouble } };
      return;
    }
    probes = {
      ...probes,
      [kind]: { status: 'ok', model: done.model, latencyMs: done.latencyMs, error: '' },
    };
  }

  /** Перечень имён моделей у поставщика — молча.
   *
   * Спрашивается он на каждую правку адреса и ключа, и непóднятый поставщик
   * отвечает отказом на каждый знак: плашка беды выскакивала бы поверх набора.
   * Не ответил — список пуст, имя вписывают руками.
   */
  async function listModels(kind) {
    const creds = kind === 'chat' ? chat : embed;
    const found = await askModels(call, { kind, ...creds });
    if (!alive.now) return;
    models = { ...models, [kind]: found.models };
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

  /** Выйти из учётной записи Telegram.
   *
   * Кнопка заперта на время зова: сервер отзывает ключ не мгновенно, и второе
   * нажатие ушло бы в уже отозванный сеанс — человек прочитал бы отказ как
   * «выйти не удалось».
   */
  async function logout() {
    leaving = false;
    leavingBusy = true;
    const done = await ask('settings.logout');
    leavingBusy = false;
    if (done === null) return;
    say('Сессия Telegram завершена');
    // Черновик стирается здесь, а не перечитыванием: `refresh` переписывает его
    // только при первом чтении, и api_id с телефоном остались бы на экране —
    // вопреки тому, что человек прочитал в подтверждении и что уже случилось в
    // базе.
    draft = { ...BLANK_TG };
    await refresh();
  }

  /** Стереть все данные приложения.
   *
   * Запор снимается и после отказа: удалить получается не всегда — на Windows
   * файл базы держит сам процесс, — и запертая навсегда кнопка означала бы, что
   * повторить попытку можно только перезапуском.
   */
  async function wipe() {
    wiping = false;
    wipingBusy = true;
    say('Удаляем данные…');
    await ask('system.wipe');
    wipingBusy = false;
  }

  $effect(() => {
    const settled = alive.mounted();
    refresh().then(() => {
      if (alive.now) {
        listModels('chat');
        listModels('embed');
      }
    });
    return () => {
      settled();
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
        busy={leavingBusy}
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
        onedit={() => forgetProbe('chat')}
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
        onedit={() => forgetProbe('embed')}
        onprobe={() => probe('embed')}
        onsame={switchSame}
      />

      <PipelineSection values={pipeline} onsave={savePipeline} />

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
          <button
            class="btn danger"
            type="button"
            disabled={wipingBusy}
            onclick={() => (wiping = true)}
          >
            <span class="material-symbols-outlined">delete_forever</span>
            Удалить всё
          </button>
        </div>
      </SettingsSection>
    {/if}
  </div>

  <!-- Окно входа стоит внутри поля настроек, а не рядом с ним: кнопки в нём
       той же плотности, что и остальные кнопки экрана, и берут они её отсюда.
       На раскладку это не влияет — окно висит поверх страницы. -->
  {#if logging}
    <TelegramLogin
      {say}
      creds={draft}
      relogin={tg.has_session}
      ondone={loggedIn}
      onclose={() => (logging = false)}
    />
  {/if}
</div>

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
