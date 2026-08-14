<script>
  // Экран журнала: страница записей из кольца, отбор по уровням, очистка.
  //
  // Зов моста и слушатель вестей приходят параметрами от оболочки: обёртка
  // отказа одна на окно, и цикл событий тоже один — второй крутил бы второй
  // опрос моста со своей отметкой виденного.

  import { call } from '$api/bridge.js';
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import LogLevelPill from '$components/LogLevelPill.svelte';
  import LogRow from '$components/LogRow.svelte';
  import {
    AT_FIRST,
    LEVELS,
    askDelay,
    emptyText,
    levelTone,
    logTime,
    mayHide,
    shown,
    toggled,
  } from '$state/logs.js';

  let { ask, events, say } = $props();

  const CLEAR_ASK =
    'Очистить буфер логов в окне?\n\nЗаписи в файле журнала и в потоке не удаляются — это только список в окне.';

  let asking = $state(false);
  let loaded = $state(false);
  let records = $state([]);
  let counts = $state({});
  let total = $state(0);
  let selected = $state(new Set(AT_FIRST));
  let following = $state(true);
  let opened = $state(new Set());

  const visible = $derived(shown(records, selected));

  let askedAt = 0;
  let timer = null;
  let alive = true;

  /** Перечитать страницу журнала целиком.
   *
   * Целиком, а не приростом: счётчики в пилюлях считают весь буфер, и собрать
   * их из одной новой записи нельзя — выпавшее из кольца ушло бы незамеченным.
   *
   * Зовём мост напрямую, а не общей обёрткой окна: у этого зова свой отказ.
   * Мост отвечает им, если журнал спрашивают чаще раза в секунду, — а спросить
   * так легко, просто вернувшись на вкладку. Общая обёртка показала бы плашку
   * и вышла молча, оставив экран в «Загрузка…» навсегда: перечитать его после
   * этого некому — зовы моста в журнал ничего не пишут, и вести не придут.
   * Поэтому первый отказ переживается тихим повтором, и только второй виден
   * человеку.
   */
  async function refresh(again = false) {
    askedAt = Date.now();
    try {
      show(await call('system.logs'));
    } catch (refusal) {
      if (!alive) return;
      if (again) return say(refusal.message, true);
      clearTimeout(timer);
      timer = setTimeout(() => refresh(true), askDelay(0));
    }
  }

  function show(page) {
    if (!alive) return;
    records = page.records;
    counts = page.level_counts;
    total = page.total;
    // Развёрнутые строки, выпавшие из кольца, забываются: иначе набор рос бы
    // до самого закрытия окна, помня номера, которых уже нет.
    const present = new Set(records.map((one) => one.id));
    opened = new Set([...opened].filter((id) => present.has(id)));
    loaded = true;
  }

  /** Перечитать не раньше, чем позволено.
   *
   * Выдержку считает `askDelay`, а не эта строка: у неё два довода, и оба
   * снаружи — пачка вестей и срок моста.
   */
  function later() {
    clearTimeout(timer);
    timer = setTimeout(refresh, askDelay(Date.now() - askedAt));
  }

  function pushed() {
    if (following) later();
  }

  function toggleLevel(id) {
    if (mayHide(selected, id)) selected = toggled(selected, id);
  }

  /** Догнать пропущенное, когда авто-обновление включили обратно.
   *
   * Пока оно было выключено, вести отбрасывались: без догона экран остался бы
   * показывать снимок той минуты, когда его выключили.
   */
  function follow(on) {
    following = on;
    if (on) later();
  }

  async function clear() {
    asking = false;
    const done = await ask('system.clear_logs');
    if (done === null) return;
    say(`Очищено ${done.cleared} записей`);
    later();
  }

  $effect(() => {
    alive = true;
    // Подписка гасится в источнике: без неё каждая запись журнала
    // превращалась бы в весть, а на чужих экранах эта работа не нужна никому.
    ask('system.watch_logs', true);
    const deaf = [
      events.on('system_log_record_pushed', pushed),
      // Потеря значит, что часть записей выпала из кольца вестей; страницу
      // после неё перечитывают целиком, чтобы счётчики не разошлись со списком.
      // Через ту же выдержку: потеря приходит как раз под нагрузкой, когда
      // мост уже на пределе своего срока.
      events.on('missed', later),
    ];
    refresh();
    return () => {
      alive = false;
      clearTimeout(timer);
      for (const off of deaf) off();
      ask('system.watch_logs', false);
    };
  });
</script>

<div class="logs-toolbar">
  <div class="logs-level-pills">
    {#each LEVELS as level (level.id)}
      <LogLevelPill
        label={level.label}
        icon={level.icon}
        tone={level.tone}
        count={counts[level.id] || 0}
        active={selected.has(level.id)}
        onpick={() => toggleLevel(level.id)}
      />
    {/each}
  </div>

  <div class="logs-toolbar-gap"></div>

  <label class="logs-auto-refresh">
    <input
      type="checkbox"
      checked={following}
      onchange={(event) => follow(event.currentTarget.checked)}
    />
    Авто-обновление
  </label>

  <button class="icon-btn" type="button" title="Очистить логи" onclick={() => (asking = true)}>
    <span class="material-symbols-outlined">cleaning_services</span>
  </button>
</div>

{#if asking}
  <ConfirmDialog
    message={CLEAR_ASK}
    confirmLabel="Очистить"
    onconfirm={clear}
    oncancel={() => (asking = false)}
  />
{/if}

<div class="logs-list">
  {#if emptyText({ loaded, total, showing: visible.length })}
    <div class="logs-empty">{emptyText({ loaded, total, showing: visible.length })}</div>
  {:else}
    {#each visible as one (one.id)}
      <LogRow
        time={logTime(one.ts)}
        level={one.level}
        tone={levelTone(one.level)}
        source={one.source}
        message={one.msg}
        details={one.details}
        expanded={opened.has(one.id)}
        ontoggle={() => (opened = toggled(opened, one.id))}
      />
    {/each}
  {/if}
</div>
