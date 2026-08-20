<script>
  // Короткие подписи, которые добавляют и снимают по одной.
  //
  // Ими названо одно и то же под разными именами: у навыка это «js» против
  // «JavaScript», у компании — написания, под которыми она приходит в
  // объявлениях. Предмет приходит списком снаружи, здесь его нет.
  import { aliasesAfter } from '$state/skills.js';

  import Chip from './Chip.svelte';

  let { items, onadd, onremove } = $props();

  let adding = $state(false);
  let draft = $state('');

  /** Закончить набор: принятое уходит наружу, отменённое пропадает.
   *
   * Что считать принятым, решает не окошко: отменённый набор и повтор в другом
   * регистре судятся одинаково у всех, кто держит такие подписи.
   */
  function finish(keep) {
    if (!adding) return;
    const after = aliasesAfter(items, draft, keep);
    adding = false;
    draft = '';
    if (after.length > items.length) onadd(after.at(-1));
  }
</script>

<div class="chips">
  {#each items as one, index (index)}
    <Chip text={one} onremove={() => onremove(index)} />
  {/each}

  {#if adding}
    <!-- Курсор ставится в поле сразу: его и завели по нажатию «добавить».
         Проверка a11y гасится нарочно — она о формах, где полей несколько и
         выбор первого за человеком. -->
    <!-- svelte-ignore a11y_autofocus -->
    <input
      class="chip-input"
      autofocus
      bind:value={draft}
      onblur={() => finish(true)}
      onkeydown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          finish(true);
        } else if (event.key === 'Escape') {
          event.preventDefault();
          finish(false);
        }
      }}
    />
  {:else}
    <button class="chip-add" type="button" onclick={() => (adding = true)}>+</button>
  {/if}
</div>
