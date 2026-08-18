<script>
  // Стек места работы: выбирают из навыков анкеты, а не набирают.
  //
  // Набирать нельзя: мост связывает место работы с заведённым навыком по
  // имени и незнакомое отбрасывает молча — человек написал бы «js», а в
  // резюме этого места стек оказался бы пуст.
  import { grouped } from '$state/skills.js';

  import Chip from './Chip.svelte';

  let { chosen, known, onadd, onremove } = $props();

  let open = $state(false);
  let query = $state('');

  const taken = $derived(new Set(chosen.map((one) => one.toLowerCase())));
  // Навыков в анкете под сотню, и плоским списком имён в них не найтись:
  // категории и уровень — то же, чем человек различает их на своей вкладке.
  const groups = $derived(
    grouped(known)
      .map((group) => ({
        name: group.name,
        items: group.items.filter((one) =>
          one.name.toLowerCase().includes(query.trim().toLowerCase()),
        ),
      }))
      .filter((group) => group.items.length > 0),
  );

  function toggle() {
    open = !open;
    query = '';
  }

  function take(name) {
    open = false;
    query = '';
    onadd(name);
  }

  // Щелчок мимо закрывает подборщик. Слушателя вешаем следующим кадром: тот же
  // щелчок, что открыл подборщик, дошёл бы до документа и закрыл его обратно.
  $effect(() => {
    if (!open) return;
    const away = (event) => {
      if (event.target.closest('.skill-picker') || event.target.closest('.chip-add')) return;
      open = false;
    };
    const later = setTimeout(() => document.addEventListener('click', away), 0);
    return () => {
      clearTimeout(later);
      document.removeEventListener('click', away);
    };
  });
</script>

<div class="skills-block">
  {#each chosen as one, index (one)}
    <Chip text={one} onremove={() => onremove(index)} />
  {/each}

  <button class="chip-add" type="button" onclick={toggle}>+ навык</button>

  {#if open}
    <div class="skill-picker">
      {#if known.length === 0}
        <div class="skill-picker-empty">Нет навыков. Добавьте в Skills.</div>
      {:else}
        <div class="skill-picker-search">
          <span class="material-symbols-outlined">search</span>
          <input placeholder="Поиск навыка..." maxlength="64" bind:value={query} />
        </div>
        <div class="skill-picker-list">
          {#each groups as group (group.name)}
            <div class="skill-picker-cat">{group.name}</div>
            {#each group.items as one (one.name)}
              <button
                class="skill-picker-item"
                class:disabled={taken.has(one.name.toLowerCase())}
                type="button"
                disabled={taken.has(one.name.toLowerCase())}
                onclick={() => take(one.name)}
              >
                <span>{one.name}</span>
                <span class="lvl">{one.level}</span>
              </button>
            {/each}
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>
