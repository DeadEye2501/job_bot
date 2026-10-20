<script>
  // Мастер первого запуска: четыре шага между пустым приложением и работающим.
  //
  // Показывается вместо окна приложения, пока настройка не доведена до конца:
  // бот без учётной записи и без модели не сделает ничего, а разбираться,
  // почему он молчит, человеку пришлось бы по журналу.
  //
  // Пройденное приходит с моста: мастер бросают на середине и открывают
  // назавтра, и начнись он снова с первого шага — человек запрашивал бы код
  // подтверждения второй раз, о чём мастер сам же и предупреждает на обложке.
  import { untrack } from 'svelte';

  import WizardFoot from '$components/WizardFoot.svelte';
  import WizardSteps from '$components/WizardSteps.svelte';
  import { living } from '$state/alive.js';
  import { backScreen, nextScreen, resumeScreen, stepAt, stepMarks } from '$state/wizard.js';

  import WizardCv from './WizardCv.svelte';
  import WizardLlm from './WizardLlm.svelte';
  import WizardTelegram from './WizardTelegram.svelte';

  let { ask, say, ondone, completed } = $props();

  // Начальное берётся один раз, нарочно: мастер стоит на своём экране, пока его
  // проходят, — следи эти двое за доводом, уход вперёд сбрасывал бы человека
  // обратно на первый непройденный шаг.
  let screen = $state(untrack(() => resumeScreen(completed)));
  let passed = $state(untrack(() => [...completed]));
  let finishing = $state(false);

  const alive = living();

  const marks = $derived(stepMarks(passed, screen));
  const back = $derived(backScreen(screen));

  /** Шаг сделан: отметить его пройденным и уйти дальше. */
  function ahead() {
    passed = [...passed, stepAt(screen)];
    screen = nextScreen(screen);
  }

  /** Последний шаг: отметить настройку законченной.
   *
   * Отметка ставится в самом конце, а не по ходу: она же поднимает бота, и
   * поставленная раньше запустила бы его без модели.
   */
  async function finish() {
    // Заперто на время полёта: `wizard.complete` поднимает бота, и второе
    // нажатие подняло бы второго на той же строке сеанса Telegram.
    if (finishing) return;
    finishing = true;
    const done = await ask('wizard.complete');
    if (!alive.now) return;
    finishing = false;
    if (done === null) return;
    passed = [...passed, stepAt(screen)];
    screen = 'done';
  }

  /** Уйти в приложение с последнего экрана.
   *
   * Окно растёт первым и растит его мост: разметка приложения нарисована шире
   * мастера, и смени оболочка экран раньше — человек увидел бы её сплющенной.
   */
  async function openApp() {
    await ask('wizard.enter_main_app');
    if (alive.now) ondone();
  }

  $effect(() => {
    const settled = alive.mounted();
    return () => {
      settled();
    };
  });
</script>

<div class="wiz-window">
  <!-- Приглушена только обложка: на финале четыре галочки горят в полную силу —
       это и есть то, ради чего мастер проходили. -->
  <WizardSteps {marks} dimmed={screen === 'welcome'} />

  {#if screen === 'welcome'}
    <div class="wiz-body">
      <div class="wiz-welcome">
        <div class="wiz-head">
          <span class="material-symbols-outlined">smart_toy</span>
          <h1>Добро пожаловать в Job Bot</h1>
        </div>
        <div class="wiz-text">
          Бот читает вакансии из Telegram-каналов, сравнивает их с вашим профилем, помогает
          вести переписку с HR и отслеживает статусы откликов. Настройка займёт 4 шага:
          <strong>Telegram</strong>, <strong>LLM</strong>, <strong>эмбеддинги</strong>,
          <strong>резюме</strong>.
        </div>
        <div class="warning-card">
          <span class="material-symbols-outlined">warning</span>
          <div>
            <strong>Заведите отдельный аккаунт для бота.</strong> Политика telegram не
            одобряет массовую автоматизированную рассылку сообщений. Есть риск полной
            блокировки аккаунта <strong>без возможности восстановления</strong>.
          </div>
        </div>
        <div class="info-card">
          <span class="material-symbols-outlined">lock</span>
          <div>
            <strong>Все ключи остаются на вашем компьютере.</strong> Telegram-сессия и API-ключи
            LLM шифруются ключом из системного хранилища паролей и лежат только в локальной БД.
            Наружу ничего не уходит.
          </div>
        </div>
      </div>
    </div>
    <WizardFoot
      nextLabel="Дальше"
      nextIcon="arrow_forward"
      onnext={() => (screen = 'telegram')}
    />
  {:else if screen === 'telegram'}
    <WizardTelegram {ask} {say} onback={() => (screen = back)} onnext={ahead} />
  {:else if screen === 'chat'}
    <WizardLlm
      {ask}
      kind="chat"
      onback={() => (screen = back)}
      onnext={ahead}
    />
  {:else if screen === 'embed'}
    <WizardLlm
      {ask}
      kind="embed"
      onback={() => (screen = back)}
      onnext={ahead}
    />
  {:else if screen === 'cv'}
    <WizardCv
      {ask}
      busy={finishing}
      onback={() => (screen = back)}
      onnext={finish}
    />
  {:else}
    <div class="wiz-body wiz-done">
      <span class="material-symbols-outlined">check_circle</span>
      <h2>Готово</h2>
      <p class="wiz-text">
        Что сделать дальше:
        <br /><br />
        1. Откройте <strong>Профиль → Skills</strong> и проверьте уровни навыков. Если резюме
        разбирала LLM — пройдитесь по списку и поправьте оценки.
        <br />
        2. В <strong>Системе → Настройки</strong> задайте порог отсева вакансий.
        <br />
        3. Добавьте каналы с вакансиями в <strong>Чат → Каналы</strong> и
        <strong>подпишитесь на них под Telegram-аккаунтом бота</strong> — иначе он не увидит
        сообщения.
      </p>
    </div>
    <WizardFoot nextLabel="Открыть Job Bot" nextIcon="arrow_forward" onnext={openApp} />
  {/if}
</div>
