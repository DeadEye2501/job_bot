<script>
  // Пилюля уровня: значок, имя и счёт записей этого уровня во всём буфере.
  let { label, icon, tone, count, active, onpick } = $props();
</script>

<button
  class="pill logs-level-pill"
  class:active
  data-tone={tone}
  type="button"
  aria-pressed={active}
  onclick={() => onpick()}
>
  <span class="material-symbols-outlined">{icon}</span>
  {label}
  <span class="count">{count}</span>
</button>
