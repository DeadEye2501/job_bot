<script>
  // Экран настроек: учётная запись Telegram, оба поставщика моделей, пороги
  // отбора, почта для откликов и удаление всех данных.
  //
  // Записывается всё по ходу, без кнопки «сохранить»: поле уезжает на мост,
  // когда его покидают. Так было и в прежнем окне, и это верно для настроек —
  // забытая кнопка означала бы бота, работающего по старому порогу.

  import { call } from '$api/bridge.js';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import LlmSection from '$components/LlmSection.svelte';
  import MailSection from '$components/MailSection.svelte';
  import PipelineSection from '$components/PipelineSection.svelte';
  import SettingsSection from '$components/SettingsSection.svelte';
  import TelegramSection from '$components/TelegramSection.svelte';
  import { living } from '$state/alive.js';
  import { providerForm } from '$state/provider_form.svelte.js';
  import {
    blankTelegram,
    canShareChat,
    credsChanged,
    embedReading,
    loginTrouble,
    mirrored,
    probePill,
    sharesChat,
    telegramCreds,
  } from '$state/settings.js';

  import TelegramLogin from './TelegramLogin.svelte';

  let { ask, say } = $props();

  const WIPE_ASK =
    'Удалить ВСЕ данные приложения?\n\nБудут стёрты база, сессия Telegram, медиафайлы и журнал. Приложение закроется. Откатить нельзя.';

  const LOGOUT_ASK =
    'Выйти из сессии Telegram?\n\nКлюч будет отозван на сервере, бот остановится, а api_id, api_hash и телефон сотрутся из настроек. Войти заново придётся с нуля.';

  let loaded = $state(false);
  let tg = $state(null);
  let draft = $state(blankTelegram());
  let pipeline = $state({});
  let mail = $state({});
  let logging = $state(false);
  let wiping = $state(false);
  let leaving = $state(false);
  // Кнопки, отпустить которые до ответа нельзя: обе делают необратимое, и
  // второе нажатие ушло бы в уже начатую работу.
  let leavingBusy = $state(false);
  let wipingBusy = $state(false);

  const alive = living();
  const chat = providerForm({ kind: 'chat', call, alive });
  const embed = providerForm({ kind: 'embed', call, alive });

  const pills = $derived({ chat: probePill(chat.probe), embed: probePill(embed.probe) });
  // Эмбеддинги ходят туда же, куда чат, только пока чат не на Claude: векторов
  // он не считает, и такую пару мост не примет.
  const sharing = $derived(
    sharesChat({ same: embed.same, fromFile: embed.fromFile, chat: chat.creds }),
  );

  /** Перечитать настройки с моста целиком.
   *
   * Зовётся на входе на экран и после того, что меняет не одно поле: вход в
   * Telegram, выход из него. После обычной записи не зовётся — снимок затёр бы
   * соседнее поле, которое человек правит прямо сейчас.
   */
  async function refresh() {
    readMail();
    const now = await ask('settings.get');
    if (now === null || !alive.now) return;
    // Плашка проверки говорит про те данные, которые проверяли: приехали
    // другие — ей верить больше нельзя.
    if (credsChanged(chat.creds, now.chat)) chat.forget();
    if (credsChanged(embed.creds, now.embed)) embed.forget();
    tg = now.tg;
    chat.creds = now.chat;
    embed.creds = now.embed;
    // Лимит агрегатора приходит в снимке агрегаторов, а стоит в строке
    // «Пайплайн» рядом с лимитом каналов и пишется тем же сохранением.
    pipeline = { ...now.pipeline, aggregator_backfill_limit: now.aggregators.aggregator_backfill_limit };
    if (!loaded) {
      draft = telegramCreds(now.tg);
      // Признаки выводятся из настроек только здесь, при первом чтении. Дальше
      // ими распоряжается человек — пересчитывай мы их при каждой записи,
      // снятая галочка возвращалась бы сама, и отдельный адрес для эмбеддингов
      // задать было бы нечем.
      ({ fromFile: embed.fromFile, same: embed.same } = embedReading(now.chat, now.embed));
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

  /** Перечитать почту: мост подставляет сервер по адресу, и записанное
   *  отличается от набранного. */
  async function readMail() {
    const now = await ask('settings.mail');
    if (now !== null && alive.now) mail = now;
  }

  /** Записать почту целиком: мост принимает её одной записью. */
  async function saveMail(part) {
    const next = { ...mail, ...part };
    mail = next;
    await ask('settings.save_mail', {
      address: next.address ?? '',
      password: next.password ?? '',
      smtp_host: next.smtp_host ?? null,
      smtp_port: next.smtp_port ?? null,
    });
    await readMail();
  }

  function saveChat(part) {
    chat.creds = { ...chat.creds, ...part };
    forgetShareOnClaude();
    // Перечень имён спрашивается заново на смене адреса или ключа: он с них и
    // читается, и оставленный прежним подсказывал бы модели чужого сервера.
    if (part.model === undefined) chat.listModels();
    // Без модели мост строку не примет: после выбора поставщика её ещё нет, и
    // уход из поля ключа дал бы плашку отказа вместо записи.
    if (!chat.creds.model) return;
    // Когда эмбеддинги ходят туда же, их адрес и ключ едут следом: иначе в
    // базе осталась бы пара, которой человек на экране не видел.
    if (!sharing) return save({ chat: chat.creds });
    embed.creds = mirrored(chat.creds, embed.creds);
    if (part.model === undefined) embed.listModels();
    return save({ chat: chat.creds, embed: embed.creds });
  }

  function saveEmbed(part) {
    embed.creds = { ...embed.creds, ...part };
    if (part.model === undefined) embed.listModels();
    if (!embed.creds.model) return;
    return save({ embed: embed.creds });
  }

  /** Человек выбрал поставщика чата по имени.
   *
   * Записи нет, пока не выбрана модель: имя прежнего поставщика у нового не
   * заведётся, а без имени мост строку не примет.
   */
  function pickPreset(label) {
    const listing = chat.pickPreset(label);
    forgetShareOnClaude();
    return listing;
  }

  /** Чат ушёл на Claude — галочка «как у чата» снимается насовсем.
   *
   * Скрытая, но взведённая, она вернулась бы отмеченной вместе с другим
   * поставщиком чата и молча затёрла бы отдельный сервер эмбеддингов.
   */
  function forgetShareOnClaude() {
    if (!canShareChat(chat.creds)) embed.same = false;
  }

  /** Спросить файл модели диалогом окна и записать его. */
  async function pickFile() {
    const got = await embed.pickFile();
    if (got.trouble) return say(got.trouble, true);
    if (got.path) return save({ embed: embed.creds });
  }

  /** Человек переключил «ходить туда же, куда чат».
   *
   * Записать при снятии нечего: прежние значения уже лежат в базе.
   */
  function switchSame(on) {
    embed.useChat(on, chat.creds);
    if (on) return save({ embed: embed.creds });
  }

  /** Проверить связь с поставщиком.
   *
   * Мосту едут черновые данные из формы, а не сохранённые: человек должен
   * узнать исход до записи — иначе проверять было бы нечего, кроме того, что
   * уже лежит в базе.
   */
  function probe(form) {
    // Пустую форму не отправляем: поставщик ответит отказом про разбор адреса,
    // и человек будет искать беду в сети вместо незаполненного поля.
    if (form.trouble) return say(form.trouble, true);
    return form.verify();
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
    draft = blankTelegram();
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
        chat.listModels();
        embed.listModels();
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

      <MailSection {mail} onsave={saveMail} onopen={(url) => ask('system.open_url', url)} />

      <LlmSection
        icon="smart_toy"
        title="LLM для чата"
        creds={chat.creds}
        models={chat.models}
        pill={pills.chat}
        busy={chat.probe.status === 'busy'}
        onsave={saveChat}
        onedit={chat.forget}
        onprobe={() => probe(chat)}
        onpreset={pickPreset}
      />

      <!-- Записи на смене источника нет, пока не выбран файл или не набран
           сервер: пустой источник мост не примет, а прежний остаётся в базе
           до тех пор. -->
      <LlmSection
        icon="scatter_plot"
        title="LLM для эмбеддингов"
        creds={embed.creds}
        models={embed.models}
        pill={pills.embed}
        busy={embed.probe.status === 'busy'}
        sameAsChat={embed.same}
        shareable={canShareChat(chat.creds)}
        fromFile={embed.fromFile}
        onsave={saveEmbed}
        onedit={embed.forget}
        onprobe={() => probe(embed)}
        onsame={switchSame}
        onsource={embed.switchSource}
        onpickfile={pickFile}
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
