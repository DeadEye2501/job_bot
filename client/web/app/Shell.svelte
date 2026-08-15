<script>
  // Оболочка окна: боковое меню, поле раздела и нижняя полоса.
  //
  // Держит состояние, общее для всего окна, и отдаёт экранам три вещи, которых
  // на окно по одной: зов моста с плашкой отказа, саму плашку и слушатель
  // вестей. Свои зовы у экранов свои — общее тут не «ходить в мост», а не
  // заводить второй плашки и второго цикла событий.
  //
  // Компоненты о мосте не знают ничего: им всё приходит параметрами, а наружу
  // уходят колбэки.

  import { call } from '$api/bridge.js';
  import { listener } from '$api/events.js';
  import { attempts } from '$state/attempts.js';
  import ContactsScreen from './ContactsScreen.svelte';
  import LogsScreen from './LogsScreen.svelte';
  import ProfileScreen from './ProfileScreen.svelte';
  import SettingsScreen from './SettingsScreen.svelte';
  import StatsScreen from './StatsScreen.svelte';
  import VacanciesScreen from './VacanciesScreen.svelte';
  import WizardScreen from './WizardScreen.svelte';
  import HealthLamp from '$components/HealthLamp.svelte';
  import ModeToggle from '$components/ModeToggle.svelte';
  import NavGroup from '$components/NavGroup.svelte';
  import Plaque from '$components/Plaque.svelte';
  import ProgressBars from '$components/ProgressBars.svelte';
  import RunButton from '$components/RunButton.svelte';
  import TopTabs from '$components/TopTabs.svelte';
  import UnreadBadge from '$components/UnreadBadge.svelte';
  import { LAMPS, allAlive, blockedTip, shouldTurnOff } from '$state/health.js';
  import { OFF } from '$state/modes.js';
  import { STARTING, bar, caption, rerunNote } from '$state/progress.js';
  import { SECTIONS, SYSTEM_TABS } from '$state/sections.js';

  const PLAQUE_MS = 2800;

  // Ход обхода, о котором ещё ничего не известно. Одним объявлением на оба
  // места: начальное состояние и сброс в начале обхода обязаны совпадать, а
  // разъедься они — второй обход начался бы с хвостом первого.
  const NOTHING_YET = { channels: { label: '', current: 0, total: 0 }, messages: { current: 0, total: 0 } };

  // Часы здоровья. Спрашивать его некому, кроме нас: вестью оно не приходит —
  // мост объявляет только то, что случилось само (`client/bridge/lifespan.py`),
  // а здоровье он меряет по вопросу. Непрочитанное часов не требует: о нём
  // весть есть, и она приходит на каждое сохранённое письмо.
  const HEALTH_EVERY_MS = 5000;

  const MODE_TITLE = 'Режим работы — клик переключает';
  const RUN_TITLE = 'Прогнать цикл прямо сейчас';
  const STOP_TITLE = 'Остановить цикл';

  // Слушатель заведён здесь, а не в эффекте: экраны получают его параметром и
  // подписываются в своих эффектах, а те срабатывают раньше нашего. Цикл при
  // этом заводит всё равно эффект — до него слушатель молчит.
  const heard = listener((after) => call('system.events', after));
  const chatTries = attempts();

  // Пока неизвестно, доведена ли настройка до конца, окно не показывает
  // ничего: мелькнувшее на миг приложение с пустыми списками человек прочтёт
  // как поломку, а не как «мастер сейчас откроется».
  let setup = $state(null);
  let section = $state(SECTIONS[0].key);
  let systemTab = $state(SYSTEM_TABS[0].key);
  let expanded = $state(false);
  let health = $state(null);
  let unread = $state(0);
  // Список непрочитанных переписок: открыт ли, ждём ли ответа и что в нём.
  let chatsOpen = $state(false);
  let chatsLoading = $state(false);
  let chats = $state([]);
  // Чью карточку открыть, придя в контакты со стороны: из списка непрочитанного
  // над полосой или из карточки вакансии. Отметка разовая: контакты сообщают,
  // что приняли её, и она гаснет. Останься она лежать — каждый следующий заход
  // в раздел заново открывал бы ту же карточку, и до остальных вкладок было бы
  // не добраться.
  let openCard = $state(null);
  let mode = $state(OFF);
  let running = $state(false);
  let crawling = $state(false);
  let channels = $state(NOTHING_YET.channels);
  let messages = $state(NOTHING_YET.messages);
  // Работа без счёта — прогон одной вакансии: полосам показать нечего, а
  // сказать есть что, и говорит она за них обеих.
  let single = $state('');
  let plaque = $state({ message: '', danger: false });

  const locked = $derived(!allAlive(health));
  const lockedTip = $derived(blockedTip(health));
  const captionText = $derived(single || caption(channels, messages));
  const sectionLabel = $derived(SECTIONS.find((one) => one.key === section).label);
  const systemTabLabel = $derived(SYSTEM_TABS.find((one) => one.key === systemTab).label);

  let plaqueTimer = null;
  let alive = true;

  /** Сказать человеку о беде. Плашка одна: вторая беда сменяет первую, а не
   *  встаёт под ней — стопка плашек закрыла бы собой экран. */
  function say(message, danger = false) {
    plaque = { message, danger };
    clearTimeout(plaqueTimer);
    plaqueTimer = setTimeout(() => {
      plaque = { message: '', danger: false };
    }, PLAQUE_MS);
  }

  /** Позвать мост, показав отказ человеку и вернув «дошло ли».
   *
   * Ходят сюда все зовы оболочки: отказ у каждого выглядит одинаково —
   * плашкой, — и разбирать его по месту значило бы написать одно и то же
   * в каждом зове оболочки.
   *
   * Ответ, пришедший после закрытия окна, отбрасывается: писать его в
   * состояние уже некуда, а плашка уехала бы в умирающую страницу.
   */
  async function ask(path, ...args) {
    try {
      const answer = await call(path, ...args);
      return alive ? answer : null;
    } catch (refusal) {
      if (alive) say(refusal.message, true);
      return null;
    }
  }

  /** Принять свежее здоровье и погасить бота, если что-то отвалилось.
   *
   * Гашение здесь, а не на мосту: решение принимает окно, потому что мост о
   * том, смотрит ли на него кто-нибудь, не знает.
   */
  async function applyHealth(fresh) {
    health = fresh;
    if (shouldTurnOff(fresh, mode)) await pickMode(OFF);
  }

  async function refresh() {
    const now = await ask('system.initial');
    if (now === null) return;
    unread = now.unread.count;
    mode = now.mode;
    await applyHealth(now.health);
  }

  /** Спросить, пройдена ли первая настройка.
   *
   * Спрашивается один раз при подъёме окна: отметку ставит сам мастер, и
   * второй раз она за жизнь окна не меняется.
   */
  async function askSetup() {
    const now = await ask('wizard.state');
    // Отказ не считается ответом: сочти мы его за «настройка пройдена», мастер
    // спрятался бы навсегда, а приложение открылось бы пустым. Спросим снова с
    // ближайшим ударом часов здоровья.
    if (now !== null) setup = now;
  }

  async function askHealth() {
    if (setup === null) askSetup();
    const fresh = await ask('system.health');
    if (fresh !== null) await applyHealth(fresh);
  }

  /** Перечитать счёт непрочитанного, а с ним и открытый список.
   *
   * Список перечитывается на месте: он висит поверх окна, и пришедшее письмо
   * иначе было бы видно счётчиком, но не строкой — до закрытия и повторного
   * открытия. Опустевший счёт список закрывает: показывать в нём нечего.
   */
  async function askUnread() {
    const answer = await ask('system.unread');
    if (answer === null) return;
    unread = answer.count;
    if (unread === 0) chatsOpen = false;
    if (chatsOpen) await askChats();
  }

  /** Перечитать список.
   *
   * Свой счёт попыток: спрашивают его и нажатием, и вестью о письме, и эти два
   * зова обгоняют друг друга — лёгший поверх свежего старый ответ показал бы
   * список без только что пришедшего.
   */
  async function askChats() {
    const mine = chatTries.next();
    chatsLoading = true;
    const answer = await ask('system.unread_chats');
    if (chatTries.stale(mine)) return;
    chatsLoading = false;
    if (answer !== null) chats = answer.chats;
  }

  /** Открыть или закрыть список непрочитанных переписок.
   *
   * Пустой счётчик не открывается вовсе: список был бы пуст, а нажатие,
   * которое ничего не показывает, читается как поломка.
   */
  async function toggleChats() {
    if (unread === 0) return;
    chatsOpen = !chatsOpen;
    if (chatsOpen) await askChats();
  }

  /** Уйти в контакты — к названной карточке.
   *
   * Приходят сюда двое: список непрочитанного над полосой и связи карточки
   * вакансии. Вкладку называет сам зовущий: человек он ищет или компанию,
   * знает он, а не раздел.
   */
  function goContacts(mark) {
    chatsOpen = false;
    openCard = mark;
    section = 'contacts';
  }

  async function pickMode(chosen) {
    if (chosen === null) return say(lockedTip);
    const answer = await ask('system.set_mode', chosen);
    if (answer !== null) mode = answer.mode;
  }

  async function toggleRun() {
    if (locked) return say(lockedTip);
    // Два зова, а не имя за тернарием: спрятанное в условие имя выпадает из шва
    // с мостом — сторож ищет его литералом на месте зова, — и разъезд с питоном
    // остался бы незамеченным до первого нажатия.
    if (running) await ask('system.stop_run');
    else await ask('system.run_now');
  }

  function started() {
    crawling = true;
    running = true;
    // Первая весть о ходе приходит не сразу: до неё полосы уже бегут, и подпись
    // под ними обязана сказать, чем бот занят.
    single = STARTING;
    channels = NOTHING_YET.channels;
    messages = NOTHING_YET.messages;
  }

  function finished() {
    crawling = false;
    running = false;
  }

  /** Подвинуть полосу, которой касается весть.
   *
   * У прогона одной вакансии счёта нет вовсе — бот шлёт нули, — и полосы по
   * нему не двигаются: двинь их, они показали бы пустоту вместо хода. Своё имя
   * он говорит подписью, а первая весть о счёте её гасит: дальше подпись
   * считают полосы.
   */
  function moved(step) {
    if (step.stage === 'rerun') single = rerunNote(step.label);
    if (step.stage === 'channel') {
      single = '';
      channels = { ...step };
    }
    if (step.stage === 'message') {
      single = '';
      messages = { current: step.current, total: step.total };
    }
  }

  function watch() {
    heard.on('ingestion_started', started);
    heard.on('ingestion_finished', finished);
    heard.on('progress_update', moved);
    heard.on('unread_changed', askUnread);
    // Потеря значит, что часть случившегося выпала из кольца: чем гадать,
    // чего именно не хватает, дешевле перечитать всё разом.
    heard.on('missed', refresh);
    heard.run();
  }

  $effect(() => {
    watch();
    const health_clock = setInterval(askHealth, HEALTH_EVERY_MS);
    askSetup();
    refresh();
    return () => {
      alive = false;
      heard.stop();
      clearInterval(health_clock);
      clearTimeout(plaqueTimer);
    };
  });
</script>

{#if setup === null}
  <div class="placeholder-content">Загрузка…</div>
{:else if !setup.wizard_completed}
  <WizardScreen {ask} {say} ondone={() => (setup = { ...setup, wizard_completed: true })} />
{:else}
<div class="app-frame" class:sidebar-expanded={expanded}>
  <aside class="sidebar">
    {#each SECTIONS as one (one.key)}
      <NavGroup
        icon={one.icon}
        label={one.label}
        active={section === one.key}
        onpick={() => (section = one.key)}
      />
    {/each}
    <div class="sidebar-spacer"></div>
    <button
      class="sidebar-toggle"
      type="button"
      title={expanded ? 'Свернуть меню' : 'Развернуть меню'}
      onclick={() => (expanded = !expanded)}
    >
      <span class="material-symbols-outlined">
        {expanded ? 'chevron_left' : 'chevron_right'}
      </span>
    </button>
  </aside>

  <main class="main">
    {#if section === 'profile'}
      <ProfileScreen {ask} />
    {:else if section === 'contacts'}
      <ContactsScreen
        {ask}
        {say}
        {lockedTip}
        {openCard}
        onopened={() => (openCard = null)}
        events={heard}
      />
    {:else if section === 'stats'}
      <StatsScreen {ask} />
    {:else if section === 'vacancies'}
      <VacanciesScreen {ask} {say} {lockedTip} events={heard} oncontacts={goContacts} />
    {:else if section === 'system'}
      <TopTabs tabs={SYSTEM_TABS} active={systemTab} onpick={(key) => (systemTab = key)} />
      {#if systemTab === 'logs'}
        <LogsScreen {ask} {say} events={heard} />
      {:else}
        <SettingsScreen {ask} {say} />
      {/if}
    {:else}
      <div class="placeholder-content">
        Раздел «{sectionLabel}» — экран ещё не реализован
      </div>
    {/if}
  </main>

  <div class="bottom-bar">
    <div class="bb-left">
      {#each LAMPS as [key, name, about] (key)}
        <HealthLamp
          {name}
          title={about}
          state={health ? (health[key] ? 'ok' : 'err') : 'unknown'}
        />
      {/each}
    </div>

    <div class="bb-center">
      {#if crawling}
        <ProgressBars
          channels={bar(channels.current, channels.total)}
          messages={bar(messages.current, messages.total)}
          text={captionText}
        />
      {/if}
    </div>

    <div class="bb-right">
      <ModeToggle
        {mode}
        disabled={locked}
        title={locked ? lockedTip : MODE_TITLE}
        onpick={pickMode}
      />
      <RunButton
        {running}
        disabled={locked}
        title={locked ? lockedTip : (running ? STOP_TITLE : RUN_TITLE)}
        onpress={toggleRun}
      />
      <UnreadBadge
        count={unread}
        open={chatsOpen}
        loading={chatsLoading}
        rows={chats}
        ontoggle={toggleChats}
        onpick={(id) => goContacts({ tab: 'people', id })}
      />
    </div>
  </div>
</div>
{/if}

<Plaque message={plaque.message} danger={plaque.danger} />
