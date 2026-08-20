<script>
  // Выбор многих из длинного перечня: кнопка со счётом выбранного, под ней
  // поиск и строки с галочками.
  //
  // Не `Dropdown`: там выбирают одно значение из десятка и списка хватает, а
  // здесь выбранных бывает несколько, а самих строк — сотни, и без поиска по
  // ним не попасть.
  //
  // Имена приходят уже просеянными: искать умеет тот, кто знает, что это за
  // имена, а список только показывает переданное.
  import { whileOpen } from '$state/outside.js';

  let { placeholder, hint, empty, names, chosen, search, onsearch, prefix = '', onpick } = $props();

  let open = $state(false);
  let root = $state(null);

  $effect(() => {
    // Нажатие мимо закрывает панель: она накрывает поля под собой, и уход
    // мыши здесь не годится — в поле поиска набирают, не двигая её вовсе.
    //
    // «Мимо» считается по своему узлу, а не по классу: перечней в панели
    // отбора два, и нажатие на соседний по классу читалось бы как нажатие в
    // себя — оба остались бы открытыми, накрыв друг друга.
    return whileOpen(open, () => root, () => (open = false));
  });
</script>

<div class="pick" bind:this={root}>
  <button class="pick-btn" type="button" onclick={() => (open = !open)}>
    <span>{chosen.size ? `Выбрано: ${chosen.size}` : placeholder}</span>
    <span class="material-symbols-outlined">{open ? 'expand_less' : 'expand_more'}</span>
  </button>
  {#if open}
    <div class="pick-panel">
      <input
        class="input"
        type="text"
        placeholder={hint}
        value={search}
        oninput={(event) => onsearch(event.currentTarget.value)}
      />
      <div class="pick-list">
        {#each names as name (name)}
          <label class="checkbox-row">
            <input type="checkbox" checked={chosen.has(name)} onchange={() => onpick(name)} />
            {prefix}{name}
          </label>
        {/each}
        {#if !names.length}<div class="empty-note">{empty}</div>{/if}
      </div>
    </div>
  {/if}
</div>
