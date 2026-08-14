<script>
  // Вкладка «Skills»: навыки по категориям, уровень и синонимы.
  //
  // Перечень правится целиком и целиком же уезжает на мост: он заменяет им
  // всё, что было. Поэтому запись идёт после каждой правки — иначе уход с
  // вкладки терял бы её молча.

  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import SkillRow from '$components/SkillRow.svelte';
  import { toggled } from '$state/chosen.js';
  import { named } from '$state/profile.js';
  import { countNote, grouped } from '$state/skills.js';
  import { plural } from '$state/words.js';

  let { ask } = $props();

  const NEW_CATEGORY = 'Новая категория';

  let loaded = $state(false);
  let skills = $state([]);
  let closed = $state(new Set());
  let leaving = $state(null);

  const groups = $derived(grouped(skills));

  let alive = true;

  async function refresh() {
    const now = await ask('profile.skills');
    if (now === null || !alive) return;
    skills = now.skills;
    loaded = true;
  }

  /** Отправить перечень целиком.
   *
   * Безымянные строки отсеиваются: свежий навык рождается пустым, и мост
   * такой не примет — а человек в этот миг ещё набирает имя.
   */
  async function save() {
    await ask('profile.save_skills', { skills: named(skills, 'name') });
  }

  function edit(skill, part) {
    skills = skills.map((one) => (one === skill ? { ...one, ...part } : one));
    return save();
  }

  function remove(skill) {
    skills = skills.filter((one) => one !== skill);
    return save();
  }

  function addSkill(category) {
    skills = [...skills, { id: null, category, name: '', level: 5, aliases: [] }];
  }

  function addCategory() {
    addSkill(NEW_CATEGORY);
  }

  function renameCategory(was, becomes) {
    if (!becomes || becomes === was) return;
    skills = skills.map((one) => (one.category === was ? { ...one, category: becomes } : one));
    return save();
  }

  function dropCategory(name) {
    leaving = null;
    skills = skills.filter((one) => one.category !== name);
    return save();
  }

  function toggleCategory(name) {
    closed = toggled(closed, name);
  }

  $effect(() => {
    alive = true;
    refresh();
    return () => {
      alive = false;
    };
  });
</script>

{#if !loaded}
  <div class="empty-note">Загрузка…</div>
{:else}
  <div class="page-head">
    <div class="page-title">
      Профиль / Skills
      <span class="page-title-meta">{countNote(skills.length, groups.length)}</span>
    </div>
  </div>

  {#each groups as group (group.name)}
    <div class="collapsible" class:collapsed={closed.has(group.name)}>
      <div class="collapsible-head">
        <button
          class="icon-btn"
          type="button"
          title={closed.has(group.name) ? 'Развернуть' : 'Свернуть'}
          onclick={() => toggleCategory(group.name)}
        >
          <span class="material-symbols-outlined">expand_more</span>
        </button>
        <input
          class="cat-name"
          maxlength="64"
          value={group.name}
          onblur={(event) => renameCategory(group.name, event.currentTarget.value.trim())}
        />
        <span class="cat-spacer"></span>
        <button class="btn" type="button" onclick={() => addSkill(group.name)}>
          <span class="material-symbols-outlined">add</span>
          Навык
        </button>
        <button
          class="icon-btn"
          type="button"
          title="Удалить категорию"
          onclick={() => (leaving = group)}
        >
          <span class="material-symbols-outlined">delete</span>
        </button>
      </div>

      {#if !closed.has(group.name)}
        {#each group.items as skill (skill)}
          <SkillRow {skill} onedit={(part) => edit(skill, part)} onremove={() => remove(skill)} />
        {/each}
      {/if}
    </div>
  {/each}

  <button class="add-more" type="button" onclick={addCategory}>+ Новая категория</button>
{/if}

{#if leaving}
  <ConfirmDialog
    message={`Удалить категорию «${leaving.name}»?\n\nВместе с ней уйдут ${leaving.items.length} ${plural(leaving.items.length, 'навык', 'навыка', 'навыков')}. Откатить нельзя.`}
    confirmLabel="Удалить"
    onconfirm={() => dropCategory(leaving.name)}
    oncancel={() => (leaving = null)}
  />
{/if}
