<script>
  // Шаг мастера: резюме.
  //
  // Единственный шаг, который можно пропустить: без резюме бот работает — он
  // не сможет только приложить его к отклику, а дописать файл человек успеет
  // потом, в анкете.
  import CvFileRow from '$components/CvFileRow.svelte';
  import WizardFoot from '$components/WizardFoot.svelte';

  let { ask, say, busy, onback, onnext } = $props();

  let cv = $state(null);
  let loaded = $state(false);

  let alive = true;

  async function refresh() {
    const now = await ask('profile.get');
    if (now === null || !alive) return;
    cv = now.cv_meta;
    loaded = true;
  }

  async function pick() {
    const now = await ask('profile.pick');
    if (now === null || !alive) return;
    return refresh();
  }

  /** Пропустить шаг.
   *
   * Записанный путь стирается: пропуск значит «резюме у бота нет», и
   * оставленный от прежней попытки файл он бы всё равно приложил.
   */
  async function skip() {
    const done = await ask('wizard.skip_cv');
    if (done === null) return;
    say('Резюме можно добавить потом, в анкете');
    return onnext();
  }

  $effect(() => {
    alive = true;
    refresh();
    return () => {
      alive = false;
    };
  });
</script>

<div class="wiz-body">
  <div class="wiz-title">Резюме</div>
  <p class="wiz-text">
    Файл уходит вложением к отклику, а его текст — в письмо, которое бот сочиняет
    для HR. Навыки из него не вынимаются: их вы впишете в анкете сами.
  </p>

  {#if loaded}
    <CvFileRow meta={cv} onreplace={pick} onopen={() => ask('profile.open')} />
  {/if}
</div>

<WizardFoot
  trouble=""
  nextLabel={cv ? 'Дальше' : 'Пропустить шаг'}
  busy={busy || !loaded}
  {onback}
  onnext={cv ? onnext : skip}
/>
