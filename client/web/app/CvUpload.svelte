<script>
  // Кнопка «Заменить» у файла резюме и окно способа: только прикрепить файл
  // или разобрать его и заполнить им анкету.
  //
  // Способ спрашивают до файла: закрытый после выбора диалог файла оставляет
  // всё как было, а спроси окно после — файл был бы уже записан.
  //
  // Путь спрашивает мост диалогом самого окна: браузер отдаёт выбранный файл
  // содержимым, а не путём, — а отклику нужен именно путь.
  import ChooseDialog from '$components/ChooseDialog.svelte';
  import { afterPick } from '$state/after_pick.js';
  import { living } from '$state/alive.js';
  import { awaited } from '$state/awaited.svelte.js';
  import { CV_WAYS, PARSE_CV } from '$state/cv_ways.js';

  let { ask, onchanged } = $props();

  let choosing = $state(false);

  // Ожидание разбора живёт вне экрана: ушедший и вернувшийся посреди разбора
  // видит кнопку запертой.
  const parsing = $derived(awaited.pending(PARSE_CV));

  const alive = living();

  function apply(row) {
    choosing = false;
    return afterPick(ask('profile.pick'), alive, () =>
      row.key === 'parse' ? parse() : onchanged(),
    );
  }

  /** Пустить разбор; итог плашкой называет оболочка.
   *
   * Ждать начинают до зова: пропавший файл и нечитаемый формат отвечают вестью
   * раньше ответа на сам зов. Анкету по итогу перечитывает эффект ниже, а не
   * этот зов: экран, открытый заново посреди разбора, сам разбора не пускал.
   */
  async function parse() {
    awaited.start(PARSE_CV, () => {});
    const started = await ask('profile.parse_cv');
    if (started === null) awaited.cancel(PARSE_CV);
  }

  // Ожидание снялось — разбор кончился, и анкета на экране уже прежняя.
  let wasParsing = awaited.pending(PARSE_CV);
  $effect(() => {
    if (wasParsing && !parsing && alive.now) onchanged();
    wasParsing = parsing;
  });

  $effect(() => alive.mounted());
</script>

<button
  class="btn"
  type="button"
  disabled={parsing}
  title={parsing ? 'Идёт разбор резюме' : null}
  onclick={() => (choosing = true)}
>
  Заменить
</button>

{#if choosing}
  <ChooseDialog
    icon="description"
    title="Резюме"
    rows={CV_WAYS}
    locked=""
    instant
    slim
    onapply={apply}
    onclose={() => (choosing = false)}
  />
{/if}
