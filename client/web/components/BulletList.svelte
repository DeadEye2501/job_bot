<script>
  // Список строк под заголовком: достижения, обязанности, «О проекте».
  // Наружу уходит перечень целиком — каким он стал после правки.
  //
  // Строка — многострочное поле, а не однострочное: достижение пишут фразой, и
  // в узкой строке видно только её начало.
  import { growing } from '$state/autosize.js';

  let { label, addLabel, items, onchange } = $props();
</script>

<div class="list-block">
  <div class="field-label">
    <span>{label}</span>
    <button class="add-link list-add" type="button" onclick={() => onchange([...items, ''])}>
      <span class="material-symbols-outlined">add</span>
      {addLabel}
    </button>
  </div>

  {#each items as text, index (index)}
    <div class="list-item">
      <span class="list-bullet">•</span>
      <textarea
        class="inline-edit list-input"
        rows="1"
        maxlength="250"
        value={text}
        use:growing={text}
        onblur={(event) => {
          const typed = event.currentTarget.value.trim();
          onchange(items.map((one, at) => (at === index ? typed : one)));
        }}
      ></textarea>
      <button
        class="remove-cross"
        type="button"
        title="Удалить"
        onclick={() => onchange(items.filter((_, at) => at !== index))}
      >
        ×
      </button>
    </div>
  {/each}
</div>
