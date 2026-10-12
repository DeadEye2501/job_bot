<script>
  // Обновление приложения: серый — проверить, акцентный — обновиться. Что
  // найдено и можно ли нажать, решает нижняя полоса и передаёт параметрами.
  let { ready, disabled, title, onpress } = $props();
</script>

<button
  class="icon-btn update-btn"
  class:has-update={ready}
  class:is-disabled={disabled}
  type="button"
  {title}
  aria-disabled={disabled}
  onclick={() => !disabled && onpress()}
>
  <span class="material-symbols-outlined">autorenew</span>
</button>
