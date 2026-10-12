<script>
  // Значок-сигнал в нижней полосе: серый, пока звать не к чему, подсвеченный,
  // когда есть к чему, — новые вакансии, свежая версия. Что подсвечено и можно
  // ли нажать, решает полоса и передаёт параметрами; `kind` — чей это значок,
  // им же выбирается цвет подсветки.
  let { icon, kind, lit, disabled, title, onpress } = $props();
</script>

<button
  class="icon-btn signal-btn {kind}"
  class:lit
  class:is-disabled={disabled}
  type="button"
  {title}
  aria-disabled={disabled}
  onclick={() => !disabled && onpress()}
>
  <span class="material-symbols-outlined">{icon}</span>
</button>
