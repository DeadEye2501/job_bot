<script>
  // Резюме в анкете: строка файла с кнопками и ссылка под ней — одним блоком.
  // `what` — какое резюме, для имён кнопок: резюме на экране два, и одно имя
  // «Открыть» у обоих не различить. «Заменить» («Добавить») у каждого своя (`replace`):
  // основное спрашивает, разобрать ли файл в анкету. Поле ссылки (`link`)
  // рисует анкета — оно часть её записи. `parsing` — файл сейчас разбирают:
  // убранный посреди разбора, он вернулся бы — разбор пишет путь в конце.
  import { cvOpenable } from '$state/profile.js';

  import CvFileRow from './CvFileRow.svelte';

  let { meta, label = '', what, parsing = false, replace, link, onopen, onclear } = $props();
</script>

<div class="input-stack">
  <CvFileRow {meta} {label}>
    {#snippet actions()}
      {@render replace()}
      <button
        class="btn"
        type="button"
        aria-label="Убрать {what}"
        disabled={!meta || parsing}
        title={parsing ? 'Идёт разбор резюме' : null}
        onclick={onclear}
      >
        Убрать
      </button>
      <button
        class="btn"
        type="button"
        aria-label="Открыть {what}"
        disabled={!cvOpenable(meta)}
        onclick={onopen}
      >
        Открыть
      </button>
    {/snippet}
  </CvFileRow>
  {@render link()}
</div>
