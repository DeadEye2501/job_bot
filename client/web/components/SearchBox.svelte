<script>
  // Строка поиска над списком.
  //
  // Крестик свой, а не системный: `type="search"` рисует его по-своему, без
  // подписи и мимо палитры, — и в тёмном окне он выглядит заплатой.
  let { value, placeholder, onsearch } = $props();

  let field;

  function clear() {
    onsearch('');
    // Фокус возвращается в поле: очистку жмут, чтобы искать заново, и без
    // возврата человек тыкал бы в поле мышью.
    field.focus();
  }
</script>

<label class="search-box">
  <span class="material-symbols-outlined">search</span>
  <input
    class="search-input"
    bind:this={field}
    type="text"
    {value}
    {placeholder}
    oninput={(event) => onsearch(event.currentTarget.value)}
  />
  {#if value}
    <button class="search-clear" type="button" title="Очистить поиск" onclick={clear}>
      <span class="material-symbols-outlined">close</span>
    </button>
  {/if}
</label>
