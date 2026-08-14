<script>
  // Ряд сегментов: выбирают несколько разом, нажатием по каждому.
  //
  // Не выпадающий список: выбранное видно всё сразу, а вариантов три-четыре —
  // раскрывать ради них нечего.
  let { options, chosen, onpick } = $props();
</script>

<div class="seg-row">
  {#each options as one (one.value)}
    <button
      class="seg"
      class:active={chosen.has(one.value)}
      type="button"
      aria-pressed={chosen.has(one.value)}
      onclick={() => onpick(one.value)}
    >
      {one.label}
    </button>
  {/each}
</div>
