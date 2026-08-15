<script>
  // Список строк под заголовком: достижения, обязанности.
  //
  // Строка — многострочное поле, а не однострочное: достижение пишут фразой, и
  // в узкой строке видно только её начало.
  let { label, addLabel, items, onedit, onadd, onremove } = $props();

  /** Растянуть строку по набранному.
   *
   * Полосы прокрутки у неё нет — она бы спорила с текстом, — и не растянутая
   * строка прятала бы вторую половину достижения.
   */
  function grow(field) {
    const fit = () => {
      field.style.height = 'auto';
      field.style.height = `${field.scrollHeight}px`;
    };
    fit();
    field.addEventListener('input', fit);
    return {
      destroy: () => field.removeEventListener('input', fit),
    };
  }
</script>

<div class="list-block">
  <div class="field-label">
    <span>{label}</span>
    <button class="list-add" type="button" onclick={() => onadd()}>
      <span class="material-symbols-outlined">add</span>
      {addLabel}
    </button>
  </div>

  {#each items as text, index (index)}
    <div class="list-item">
      <span class="list-bullet">•</span>
      <textarea
        class="list-input"
        rows="1"
        maxlength="250"
        value={text}
        use:grow
        onblur={(event) => onedit(index, event.currentTarget.value.trim())}
      ></textarea>
      <button class="icon-btn" type="button" title="Удалить" onclick={() => onremove(index)}>
        <span class="material-symbols-outlined">close</span>
      </button>
    </div>
  {/each}
</div>
