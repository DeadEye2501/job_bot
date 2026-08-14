<script>
  // Оболочка окна: собирает боковое меню, поле раздела и нижнюю полосу и
  // связывает их с мостом.
  //
  // Единственное место, которое ходит в мост и держит живое состояние окна.
  // Компоненты о мосте не знают ничего — им всё приходит параметрами, а
  // наружу уходят колбэки.

  import { call } from '$api/bridge.js';
  import { listener } from '$api/events.js';
  import HealthLamp from '$components/HealthLamp.svelte';
  import ModeToggle from '$components/ModeToggle.svelte';
  import NavGroup from '$components/NavGroup.svelte';
  import Plaque from '$components/Plaque.svelte';
  import ProgressBars from '$components/ProgressBars.svelte';
  import RunButton from '$components/RunButton.svelte';
  import UnreadBadge from '$components/UnreadBadge.svelte';
  import { LAMPS, allAlive, blockedTip, shouldTurnOff } from '$state/health.js';
  import { OFF } from '$state/modes.js';
  import { bar, caption } from '$state/progress.js';
  import { SECTIONS } from '$state/sections.js';

  const PLAQUE_MS = 2800;

  // Ход обхода, о котором ещё ничего не известно. Одним объявлением на оба
  // места: начальное состояние и сброс в начале обхода обязаны совпадать, а
  // разъедься они — второй обход начался бы с хвостом первого.
  const NOTHING_YET = { channels: { label: '', current: 0, total: 0 }, messages: { current: 0, total: 0 } };

  // Часы страницы. У домена своих нет вовсе — он отвечает по вопросу, — и
  // спрашивать здоровье некому, кроме нас: вестью оно не приходит. Пять секунд
  // и пятнадцать взяты у прежнего окна: столько же били его таймеры.
  const HEALTH_EVERY_MS = 5000;
  const UNREAD_EVERY_MS = 15000;

  const MODE_TITLE = 'Режим бота: выключен, только переписка, полный вперёд';
  const RUN_TITLE = 'Обход каналов помимо расписания';

  let section = $state(SECTIONS[0].key);
  let expanded = $state(false);
  let health = $state(null);
  let unread = $state(0);
  let mode = $state(OFF);
  let running = $state(false);
  let crawling = $state(false);
  let channels = $state(NOTHING_YET.channels);
  let messages = $state(NOTHING_YET.messages);
  let plaque = $state({ message: '', danger: false });

  const locked = $derived(!allAlive(health));
  const lockedTip = $derived(blockedTip(health));
  const captionText = $derived(caption(channels, messages));
  const sectionLabel = $derived(SECTIONS.find((one) => one.key === section).label);

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

  async function askHealth() {
    const fresh = await ask('system.health');
    if (fresh !== null) await applyHealth(fresh);
  }

  async function askUnread() {
    const answer = await ask('system.unread');
    if (answer !== null) unread = answer.count;
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
    channels = NOTHING_YET.channels;
    messages = NOTHING_YET.messages;
  }

  function finished() {
    crawling = false;
    running = false;
  }

  /** Подвинуть полосу, которой касается весть.
   *
   * Стадий у вести больше двух — есть ещё прогон одной вакансии и восстановление,
   * — но зажечь их сегодня некому: обе приходят с экрана вакансий, а он
   * переезжает частью Б. Разбор им пишется вместе с ним, иначе он приедет сюда
   * непроверенным и незамеченным.
   */
  function moved(step) {
    if (step.stage === 'channel') channels = { ...step };
    if (step.stage === 'message') messages = { current: step.current, total: step.total };
  }

  function watch() {
    const events = listener((after) => call('system.events', after));
    events.on('ingestion_started', started);
    events.on('ingestion_finished', finished);
    events.on('progress_update', moved);
    events.on('unread_changed', askUnread);
    // Потеря значит, что часть случившегося выпала из кольца: чем гадать,
    // чего именно не хватает, дешевле перечитать всё разом.
    events.on('missed', refresh);
    events.run();
    return events;
  }

  $effect(() => {
    const events = watch();
    const health_clock = setInterval(askHealth, HEALTH_EVERY_MS);
    const unread_clock = setInterval(askUnread, UNREAD_EVERY_MS);
    refresh();
    return () => {
      alive = false;
      events.stop();
      clearInterval(health_clock);
      clearInterval(unread_clock);
      clearTimeout(plaqueTimer);
    };
  });
</script>

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
    <div class="placeholder-content">
      Раздел «{sectionLabel}» — экран ещё не переехал
    </div>
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
        title={locked ? lockedTip : RUN_TITLE}
        onpress={toggleRun}
      />
      <UnreadBadge count={unread} />
    </div>
  </div>
</div>

<Plaque message={plaque.message} danger={plaque.danger} />
