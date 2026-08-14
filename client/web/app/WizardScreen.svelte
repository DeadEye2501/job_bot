<script>
  // Мастер первого запуска: четыре шага между пустым приложением и работающим.
  //
  // Показывается вместо окна приложения, пока настройка не доведена до конца:
  // бот без учётной записи и без модели не сделает ничего, а разбираться,
  // почему он молчит, человеку пришлось бы по журналу.
  //
  // Пройденное считает мост по самим настройкам, а не по тому, куда человек
  // нажимал: закрытое посреди установки окно иначе теряло бы весь ход.
  import WizardFoot from '$components/WizardFoot.svelte';
  import WizardSteps from '$components/WizardSteps.svelte';
  import { backScreen, nextScreen, stepMarks } from '$state/wizard.js';

  import WizardCv from './WizardCv.svelte';
  import WizardLlm from './WizardLlm.svelte';
  import WizardTelegram from './WizardTelegram.svelte';

  let { ask, say, ondone } = $props();

  let screen = $state('welcome');
  let completed = $state([]);
  let finishing = $state(false);

  let alive = true;

  const marks = $derived(stepMarks(completed, screen));
  const back = $derived(backScreen(screen));

  async function refresh() {
    const now = await ask('wizard.state');
    if (now === null || !alive) return;
    completed = now.completed;
  }

  /** Шаг сделан: перечитать пройденное и уйти дальше.
   *
   * Отметки перечитываются с моста, а не проставляются здесь: он смотрит в
   * записанные настройки и потому не соврёт про шаг, где запись не удалась.
   */
  async function ahead() {
    await refresh();
    if (alive) screen = nextScreen(screen);
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
    await refresh();
    const done = await ask('wizard.complete');
    if (!alive) return;
    finishing = false;
    if (done === null) return;
    screen = 'done';
  }

  $effect(() => {
    alive = true;
    refresh();
    return () => {
      alive = false;
    };
  });
</script>

<div class="wiz-window">
  <WizardSteps {marks} dimmed={screen === 'welcome' || screen === 'done'} />

  {#if screen === 'welcome'}
    <div class="wiz-body">
      <div class="wiz-head">
        <span class="material-symbols-outlined">smart_toy</span>
        <h1>Job Bot</h1>
      </div>
      <p class="wiz-text">
        Бот читает каналы с вакансиями, разбирает объявления моделью, сравнивает
        их с вашей анкетой и пишет тем, чьи вакансии подошли. Настройка занимает
        четыре шага и делается один раз.
      </p>
      <p class="wiz-text">
        Всё, что вы здесь введёте, остаётся на этом компьютере: ключи лежат в
        базе рядом с приложением, а к моделям оно ходит с вашей машины напрямую.
      </p>
    </div>
    <WizardFoot nextLabel="Начать" onnext={() => (screen = 'telegram')} />
  {:else if screen === 'telegram'}
    <WizardTelegram {ask} {say} onback={() => (screen = back)} onnext={ahead} />
  {:else if screen === 'chat'}
    <WizardLlm
      {ask}
      kind="chat"
      icon="smart_toy"
      title="Модель для разбора и писем"
      onback={() => (screen = back)}
      onnext={ahead}
    />
  {:else if screen === 'embed'}
    <WizardLlm
      {ask}
      kind="embed"
      icon="calculate"
      title="Модель для сравнения с анкетой"
      onback={() => (screen = back)}
      onnext={ahead}
    />
  {:else if screen === 'cv'}
    <WizardCv {ask} {say} busy={finishing} onback={() => (screen = back)} onnext={finish} />
  {:else}
    <div class="wiz-body wiz-done">
      <span class="material-symbols-outlined">check_circle</span>
      <h2>Готово</h2>
      <p class="wiz-text">
        Бот поднят. Впишите навыки и опыт в анкете, добавьте каналы в разделе
        «Контакты» — и включите обход в нижней полосе окна.
      </p>
    </div>
    <WizardFoot nextLabel="Открыть приложение" onnext={ondone} />
  {/if}
</div>
