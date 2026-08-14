<script>
  // Короткие подписи, которые добавляют и снимают по одной.
  //
  // Ими названо одно и то же под разными именами: у навыка это «js» против
  // «JavaScript», у компании — написания, под которыми она приходит в
  // объявлениях. Предмет приходит списком снаружи, здесь его нет.
  let { items, onadd, onremove } = $props();

  let adding = $state(false);
  let draft = $state('');

  function accept() {
    const value = draft.trim();
    adding = false;
    draft = '';
    if (value) onadd(value);
  }
</script>

<div class="chips">
  {#each items as one, index (index)}
    <span class="chip">
      {one}
      <button class="chip-x" type="button" title="убрать" onclick={() => onremove(index)}>×</button>
    </span>
  {/each}

  {#if adding}
    <!-- svelte-ignore a11y_autofocus -->
    <input
      class="chip-input"
      autofocus
      bind:value={draft}
      onblur={accept}
      onkeydown={(event) => event.key === 'Enter' && accept()}
    />
  {:else}
    <button class="chip-add" type="button" onclick={() => (adding = true)}>+</button>
  {/if}
</div>
