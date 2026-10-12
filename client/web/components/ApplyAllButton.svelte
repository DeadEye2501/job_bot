<script>
  // Отклик на все новые вакансии. Сам не знает ни числа, ни прогона: всё
  // приходит параметрами от нижней полосы.
  let { count, disabled, title, onpress } = $props();
</script>

<button
  class="icon-btn apply-all-btn"
  class:has-new={count > 0}
  class:is-disabled={disabled}
  type="button"
  {title}
  aria-disabled={disabled}
  onclick={() => !disabled && onpress()}
>
  <span class="material-symbols-outlined">error</span>
</button>
