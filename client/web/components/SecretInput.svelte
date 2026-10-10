<script>
  // Поле для секрета: скрыто точками, открывается глазом рядом.
  //
  // Секреты живут в этом же окне и в сеть не уходят, поэтому показать их можно
  // — но не по умолчанию: экран настроек открывают и при свидетелях.
  //
  // `mono` просит шаг мастера: ключ там стоит под адресом, набранным
  // моноширинным, и пропорциональный рядом читался бы как поле другого рода.
  //
  // `onhelp` — объяснение, где взять этот секрет; есть он — справа от глаза
  // встаёт вопрос. `autofocus` просит окно, открытое затем, чтобы в поле набрали.
  let {
    value,
    placeholder,
    mono = false,
    maxlength = null,
    autofocus = false,
    onsave,
    onhelp = null,
  } = $props();

  let shown = $state(false);
</script>

<div class="secret-input">
  <!-- Проверка a11y гасится нарочно: фокус просит только окно об одном поле. -->
  <!-- svelte-ignore a11y_autofocus -->
  <input
    class="input"
    class:mono
    type={shown ? 'text' : 'password'}
    {maxlength}
    {autofocus}
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
  {#if onhelp}
    <button class="icon-btn" type="button" title="Где это взять" onclick={() => onhelp()}>
      <span class="material-symbols-outlined">help</span>
    </button>
  {/if}
</div>
