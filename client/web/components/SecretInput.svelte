<script>
  // Поле для секрета: скрыто точками, открывается глазом рядом.
  //
  // Секреты живут в этом же окне и в сеть не уходят, поэтому показать их можно
  // — но не по умолчанию: экран настроек открывают и при свидетелях.
  let { value, placeholder, onsave } = $props();

  let shown = $state(false);
</script>

<div class="secret-input">
  <input
    class="input"
    type={shown ? 'text' : 'password'}
    {value}
    {placeholder}
    onblur={(event) => onsave(event.currentTarget.value)}
  />
  <button
    class="icon-btn"
    type="button"
    title={shown ? 'Скрыть' : 'Показать'}
    onclick={() => (shown = !shown)}
  >
    <span class="material-symbols-outlined">{shown ? 'visibility_off' : 'visibility'}</span>
  </button>
</div>
