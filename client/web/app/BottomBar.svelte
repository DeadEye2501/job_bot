<script>
  // Нижняя полоса окна: лампочки систем, ход обхода, режим, запуск и
  // непрочитанное.
  //
  // Своей сборкой, а не куском оболочки: у полосы своё состояние и своя работа
  // — часы здоровья, счёт непрочитанного, вести о ходе обхода, — и лежала она в
  // самом большом файле фронта вместе с боковым меню и полем раздела. Две
  // несвязанные работы садились на один файл, и правки в них сталкивались.
  //
  // Мост и плашку берёт доводами, как их берут экраны. Наружу отдаёт две вещи:
  // подсказку о запертых кнопках — её оболочка раздаёт экранам — и уход в
  // контакты из списка непрочитанного.
  import HealthLamp from '$components/HealthLamp.svelte';
  import HumanPlate from '$components/HumanPlate.svelte';
  import ModeToggle from '$components/ModeToggle.svelte';
  import ProgressBars from '$components/ProgressBars.svelte';
  import RunButton from '$components/RunButton.svelte';
  import UnreadBadge from '$components/UnreadBadge.svelte';
  import { attempts } from '$state/attempts.js';
  import { LAMPS, allAlive, blockedTip, shouldTurnOff } from '$state/health.js';
  import { OFF } from '$state/modes.js';
  import {
    COUNTLESS_STAGES,
    STARTING,
    bar,
    caption,
    countlessNote,
    humanText,
  } from '$state/progress.js';
  import { round } from '$state/round.svelte.js';

  let { ask, say, events, onlocked, oncontact } = $props();

  // Ход обхода, о котором ещё ничего не известно. Одним объявлением на оба
  // места: начальное состояние и сброс в начале обхода обязаны совпадать, а
  // разъедься они — второй обход начался бы с хвостом первого.
  const NOTHING_YET = { channels: { label: '', current: 0, total: 0 }, messages: { current: 0, total: 0 } };

  // Часы здоровья. Спрашивать его некому, кроме нас: вестью оно не приходит —
  // мост объявляет только то, что случилось само (`client/bridge/lifespan.py`),
  // а здоровье он меряет по вопросу. Непрочитанное часов не требует: о нём
  // весть есть, и она приходит на каждое сохранённое письмо.
  const HEALTH_EVERY_MS = 5000;

  const RUN_TITLE = 'Прогнать цикл прямо сейчас';
  const STOP_TITLE = 'Остановить цикл';

  const chatTries = attempts();

  let health = $state(null);
  let unread = $state(0);
  // Список непрочитанных переписок: открыт ли, ждём ли ответа и что в нём.
  let chatsOpen = $state(false);
  let chatsLoading = $state(false);
  let chats = $state([]);
  let mode = $state(OFF);
  let channels = $state(NOTHING_YET.channels);
  let messages = $state(NOTHING_YET.messages);
  // Работа без счёта — прогон одной вакансии: полосам показать нечего, а
  // сказать есть что, и говорит она за них обеих.
  let single = $state('');

  const locked = $derived(!allAlive(health));
  const lockedTip = $derived(blockedTip(health));
  const captionText = $derived(single || caption(channels, messages));

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
   *
   * К общему зову (`state/fresh.js`) не сведён нарочно: у него отказ моста,
   * ушедший экран и обогнанный ответ означают одно, а здесь — разное.
   * Устаревший уходит, не погасив «Загрузка…», — гасит её тот, кто пришёл
   * последним; отказ гасит её и оставляет прежний список, потому что полоса
   * живёт, пока живёт окно, и заменить показанное пустотой значило бы стереть
   * непрочитанное на первом же обрыве.
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
    if (round.running) await ask('system.stop_run');
    else await ask('system.run_now');
  }

  function started() {
    // Первая весть о ходе приходит не сразу: до неё полосы уже бегут, и подпись
    // под ними обязана сказать, чем бот занят.
    single = STARTING;
    channels = NOTHING_YET.channels;
    messages = NOTHING_YET.messages;
  }

  /** Подвинуть полосу, которой касается весть.
   *
   * У прогона одной вакансии и у разбора вставленного объявления счёта нет
   * вовсе — бот шлёт нули, — и полосы по ним не двигаются: двинь их, они показали бы пустоту вместо хода. Своё имя
   * он говорит подписью, а первая весть о счёте её гасит: дальше подпись
   * считают полосы.
   */
  function moved(step) {
    if (COUNTLESS_STAGES.has(step.stage)) single = countlessNote(step.label);
    // Агрегатор обходится той же полосой, что канал: источник за источником, и
    // подпись его — имя сайта со счётом найденного.
    if (step.stage === 'channel' || step.stage === 'aggregator') {
      single = '';
      channels = { ...step };
    }
    if (step.stage === 'message') {
      single = '';
      messages = { current: step.current, total: step.total };
    }
  }

  // Подсказку отдаём наверх производным, а не из двери, за которой меняется
  // здоровье: до первого ответа моста она говорит «проверяем», и экраны на это
  // время запирают свои кнопки. Скажи мы её только с ответом — отклик и
  // переразбор были бы открыты при неизвестном здоровье, а отпертая на миг
  // раньше правды кнопка запускает бота без модели.
  $effect(() => onlocked(lockedTip));

  $effect(() => {
    const deaf = [
      // Весть о начале слушает общий учёт (`state/round.svelte.js`), а полосе
      // он говорит о ней в тот же миг: ход прошлого прогона стирается.
      round.onStart(started),
      events.on('progress_update', moved),
      // Слово обхода — почему он снят: капча не пройдена, лимит исчерпан.
      events.on('round_note', (note) => say(note.text)),
      events.on('unread_changed', askUnread),
      // Потеря значит, что часть случившегося выпала из кольца: чем гадать,
      // чего именно не хватает, дешевле перечитать всё разом.
      events.on('missed', refresh),
    ];
    const clock = setInterval(askHealth, HEALTH_EVERY_MS);
    refresh();
    return () => {
      deaf.forEach((off) => off());
      clearInterval(clock);
    };
  });
</script>

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
    {#if round.human}
      <HumanPlate
        text={humanText(round.human)}
        onreveal={() => ask('system.reveal_browser')}
        ondone={() => ask('system.human_done')}
      />
    {:else if round.running}
      <ProgressBars
        channels={bar(channels.current, channels.total)}
        messages={bar(messages.current, messages.total)}
        text={captionText}
      />
    {/if}
  </div>

  <div class="bb-right">
    <!-- Подсказка только у запертого переключателя: у отпертого рядом стоит
         сам режим словом, и объяснять, что по нему нажимают, нечего. -->
    <ModeToggle {mode} disabled={locked} title={locked ? lockedTip : null} onpick={pickMode} />
    <RunButton
      running={round.running}
      disabled={locked}
      title={locked ? lockedTip : (round.running ? STOP_TITLE : RUN_TITLE)}
      onpress={toggleRun}
    />
    <UnreadBadge
      count={unread}
      open={chatsOpen}
      loading={chatsLoading}
      rows={chats}
      ontoggle={toggleChats}
      onpick={(id) => {
        // Список гасим здесь: он висит поверх окна прозрачным ловцом нажатий, и
        // оставленный открытым съедал бы первое нажатие в карточке, куда сам же
        // и увёл.
        chatsOpen = false;
        oncontact({ tab: 'people', id });
      }}
    />
  </div>
</div>
