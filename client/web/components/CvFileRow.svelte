<script>
  // Файл резюме: что за файл лежит, и кнопки к нему. Кнопки у каждого места
  // свои (`actions`): анкета файл заменяет и открывает, мастер только выбирает.
  import { cvNote } from '$state/profile.js';

  let { meta, actions } = $props();

  const note = $derived(cvNote(meta));
</script>

<div class="pdf-row" class:has-file={!!meta}>
  <span class="material-symbols-outlined">{meta ? 'description' : 'upload_file'}</span>
  <div class="pdf-info">
    <div class="pdf-name">{note.name}</div>
    {#if note.note}
      <div class="pdf-meta">{note.note}</div>
    {/if}
  </div>
  <div class="pdf-actions">
    {@render actions()}
  </div>
</div>
