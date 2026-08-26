<script>
  // Оболочка окна: боковое меню и поле раздела.
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
  import { living } from '$state/alive.js';
  import { blockedTip } from '$state/health.js';
  import BottomBar from './BottomBar.svelte';
  import ContactsScreen from './ContactsScreen.svelte';
  import LogsScreen from './LogsScreen.svelte';
  import ProfileScreen from './ProfileScreen.svelte';
  import SettingsScreen from './SettingsScreen.svelte';
  import StatsScreen from './StatsScreen.svelte';
  import VacanciesScreen from './VacanciesScreen.svelte';
  import WizardScreen from './WizardScreen.svelte';
  import NavGroup from '$components/NavGroup.svelte';
  import Plaque from '$components/Plaque.svelte';
  import TopTabs from '$components/TopTabs.svelte';
  import { SECTIONS, SYSTEM_TABS } from '$state/sections.js';

  const PLAQUE_MS = 2800;

  // Как часто переспрашивать про первую настройку, пока она неизвестна. Свои
  // часы, а не удар часов здоровья: те бьёт нижняя полоса, а она поднимается
  // только после того, как настройка стала известна, — до тех пор окно
  // показывает «Загрузка…», и переспросить было бы некому.
  const SETUP_RETRY_MS = 5000;

  // Слушатель заведён здесь, а не в эффекте: экраны получают его параметром и
  // подписываются в своих эффектах, а те срабатывают раньше нашего. Цикл при
  // этом заводит всё равно эффект — до него слушатель молчит.
  const heard = listener((after) => call('system.events', after));

  // Пока неизвестно, доведена ли настройка до конца, окно не показывает
  // ничего: мелькнувшее на миг приложение с пустыми списками человек прочтёт
  // как поломку, а не как «мастер сейчас откроется».
  let setup = $state(null);
  let section = $state(SECTIONS[0].key);
  let systemTab = $state(SYSTEM_TABS[0].key);
  let expanded = $state(false);
  // Чью карточку открыть, придя в контакты со стороны: из списка непрочитанного
  // над полосой или из карточки вакансии. Отметка разовая: контакты сообщают,
  // что приняли её, и она гаснет. Останься она лежать — каждый следующий заход
  // в раздел заново открывал бы ту же карточку, и до остальных вкладок было бы
  // не добраться.
  let openCard = $state(null);
  // Какую вакансию открыть, придя в раздел вакансий из мини-списка чужой
  // карточки. Отметка такая же разовая, как и та, что ведёт в контакты.
  let openVacancy = $state(null);
  // С каким отбором открыть список вакансий, придя из статистики. Отметка
  // разовая по той же причине: оставленная лежать, она навязывала бы
  // позавчерашний статус каждому следующему заходу в раздел.
  let openFilter = $state(null);
  let plaque = $state({ message: '', danger: false });
  // Подсказку о запертых кнопках считает нижняя полоса — здоровье живёт там, —
  // а раздают её экраны: у них те же кнопки заперты той же причиной. Начальное
  // значение спрашивается у того же правила: до первого ответа моста здоровье
  // неизвестно, и кнопки бота на это время заперты — отпертая на миг раньше
  // правды запускает его без модели.
  let lockedTip = $state(blockedTip(null));

  let plaqueTimer = null;
  let setupClock = null;
  const alive = living();

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
      return alive.now ? answer : null;
    } catch (refusal) {
      if (alive.now) say(refusal.message, true);
      return null;
    }
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
    // ближайшим ударом своих часов.
    if (now === null) return;
    setup = now;
    clearInterval(setupClock);
  }

  /** Уйти в контакты — к названной карточке.
   *
   * Приходят сюда двое: список непрочитанного над полосой и связи карточки
   * вакансии. Вкладку называет сам зовущий: человек он ищет или компанию,
   * знает он, а не раздел.
   */
  function goContacts(mark) {
    openCard = mark;
    section = 'contacts';
  }

  /** Уйти к вакансии — из мини-списка в карточке канала, компании или человека.
   *
   * Оттуда и смотрят, что канал принёс: увидел строку — открыл её саму.
   */
  function goVacancy(id) {
    openVacancy = { id };
    section = 'vacancies';
  }

  /** Уйти в вакансии с готовым отбором — из строки статуса в статистике.
   *
   * Иначе число в карточке остаётся числом: чтобы посмотреть, что за девять
   * штук, человеку пришлось бы идти в вакансии и набирать тот же отбор руками.
   */
  function goSlice(filter) {
    openFilter = { filter };
    section = 'vacancies';
  }

  $effect(() => {
    const settled = alive.mounted();
    // Долгие кнопки — прогон канала, прогон вакансии, отправка отклика —
    // отвечают «пущено» и уходят работать; чем кончилось, говорит эта весть.
    // Показывает её оболочка, а не карточка: работа переживает и закрытую
    // карточку, и уход на соседний экран, а сказать о ней надо всё равно.
    heard.on('action_finished', (done) => say(done.message, done.danger));
    // Цикл вестей пускается здесь: подписки экранов и полосы встают в их
    // эффектах, а пропущенное между подъёмом и подпиской доберёт первый же
    // вопрос — очередь отдаёт всё, что накопилось после названного номера.
    heard.run();
    askSetup();
    setupClock = setInterval(askSetup, SETUP_RETRY_MS);
    return () => {
      settled();
      heard.stop();
      clearInterval(setupClock);
      clearTimeout(plaqueTimer);
    };
  });
</script>

{#if setup === null}
  <div class="placeholder-content">Загрузка…</div>
{:else if !setup.wizard_completed}
  <WizardScreen
    {ask}
    {say}
    events={heard}
    completed={setup.completed}
    ondone={() => (setup = { ...setup, wizard_completed: true })}
  />
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
        onvacancy={goVacancy}
        events={heard}
      />
    {:else if section === 'stats'}
      <StatsScreen {ask} onslice={goSlice} onchannel={(id) => goContacts({ tab: 'channels', id })} />
    {:else if section === 'vacancies'}
      <VacanciesScreen
        {ask}
        {say}
        {lockedTip}
        events={heard}
        oncontacts={goContacts}
        open={openVacancy}
        onopened={() => (openVacancy = null)}
        openFilter={openFilter}
        onfiltered={() => (openFilter = null)}
      />
    {:else if section === 'system'}
      <TopTabs tabs={SYSTEM_TABS} active={systemTab} onpick={(key) => (systemTab = key)} />
      {#if systemTab === 'logs'}
        <LogsScreen {ask} {say} events={heard} />
      {:else}
        <SettingsScreen {ask} {say} />
      {/if}
    {/if}
  </main>

  <BottomBar
    {ask}
    {say}
    events={heard}
    onlocked={(tip) => (lockedTip = tip)}
    oncontact={goContacts}
  />
</div>
{/if}

<Plaque message={plaque.message} danger={plaque.danger} />
