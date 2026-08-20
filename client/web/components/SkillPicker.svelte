<script>
  // Стек места работы: выбирают из навыков анкеты, а не набирают.
  //
  // Набирать нельзя: мост связывает место работы с заведённым навыком по
  // имени и незнакомое отбрасывает молча — человек написал бы «js», а в
  // резюме этого места стек оказался бы пуст.
  import { closeOnClickAway } from '$state/outside.js';
  import { groupsMatching } from '$state/skills.js';

  import Chip from './Chip.svelte';
  import SearchBox from './SearchBox.svelte';

  let { chosen, known, onadd, onremove } = $props();

  let open = $state(false);
  let query = $state('');
  // Узел, по которому считается «нажали мимо». Своим, а не по имени класса:
  // подборщиков на вкладке столько же, сколько мест работы, и нажатие в
  // соседний по классу читалось бы как нажатие в себя — оба остались бы
  // открытыми разом.
  let root = $state(null);

  const taken = $derived(new Set(chosen.map((one) => one.toLowerCase())));
  // Навыков в анкете под сотню, и плоским списком имён в них не найтись:
  // категории и уровень — то же, чем человек различает их на своей вкладке.
  const groups = $derived(groupsMatching(known, query));

  function toggle() {
    open = !open;
    query = '';
  }

  function take(name) {
    open = false;
    query = '';
    onadd(name);
  }

  $effect(() => {
    if (!open) return;
    return closeOnClickAway(() => root, () => (open = false));
  });
</script>

<div class="skills-block" bind:this={root}>
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
          <SearchBox
            value={query}
            placeholder="Поиск навыка..."
            maxlength={64}
            onsearch={(text) => (query = text)}
          />
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
