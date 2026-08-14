<script>
  // Стек места работы: выбирают из навыков анкеты, а не набирают.
  //
  // Набирать нельзя: мост связывает место работы с заведённым навыком по
  // имени и незнакомое отбрасывает молча — человек написал бы «js», а в
  // резюме этого места стек оказался бы пуст.
  let { chosen, known, onadd, onremove } = $props();

  let open = $state(false);

  const free = $derived(known.filter((one) => !chosen.includes(one)));
</script>

<div class="chips">
  {#each chosen as one, index (one)}
    <span class="chip">
      {one}
      <button class="chip-x" type="button" title="убрать" onclick={() => onremove(index)}>×</button>
    </span>
  {/each}

  {#if free.length}
    <div class="cdd" class:open>
      <button class="chip-add" type="button" onclick={() => (open = !open)}>+</button>
      {#if open}
        <div class="cdd-panel" role="listbox" tabindex="-1" onmouseleave={() => (open = false)}>
          {#each free as one (one)}
            <button
              class="cdd-option"
              type="button"
              onclick={() => {
                open = false;
                onadd(one);
              }}
            >
              {one}
            </button>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>
