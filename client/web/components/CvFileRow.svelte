<script>
  // Файл резюме: что за файл лежит и что с ним можно сделать.
  import { cvNote } from '$state/profile.js';

  let { meta, onreplace, onopen } = $props();

  const note = $derived(cvNote(meta));
</script>

<div class="pdf-row">
  <span class="material-symbols-outlined">description</span>
  <div class="pdf-info">
    <div class="pdf-name">{note.name}</div>
    <div class="pdf-meta">{note.note}</div>
  </div>
  <div class="pdf-actions">
    <button class="btn" type="button" onclick={() => onreplace()}>Заменить</button>
    <!-- Открывать нечего, когда файла нет на диске: система показала бы свою
         ошибку вместо нашей строки «файл не найден». -->
    <button class="btn" type="button" disabled={note.missing || !meta} onclick={() => onopen()}>
      Открыть
    </button>
  </div>
</div>
