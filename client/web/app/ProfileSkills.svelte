<script>
  // Вкладка «Skills»: навыки по категориям, уровень и синонимы.
  //
  // Перечень правится целиком и целиком же уезжает на мост: он заменяет им
  // всё, что было. Поэтому запись идёт после каждой правки — иначе уход с
  // вкладки терял бы её молча.

  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import SkillRow from '$components/SkillRow.svelte';
  import { living } from '$state/alive.js';
  import { toggled, without } from '$state/chosen.js';
  import { oneWrite } from '$state/one_write.js';
  import { named } from '$state/profile.js';
  import { countNote, grouped } from '$state/skills.js';

  let { ask } = $props();

  const NEW_CATEGORY = 'Новая категория';

  let loaded = $state(false);
  let skills = $state([]);
  let closed = $state(new Set());
  let leaving = $state(null);

  const groups = $derived(grouped(skills));

  const alive = living();

  async function refresh() {
    const now = await ask('profile.skills');
    if (now === null || !alive.now) return;
    skills = now.skills;
    loaded = true;
  }

  const write = oneWrite((going) => ask('profile.save_skills', { skills: going }));

  /** Отправить перечень целиком.
   *
   * Безымянные строки отсеиваются: свежий навык рождается пустым, и мост
   * такой не примет — а человек в этот миг ещё набирает имя.
   */
  function save() {
    return write(named(skills, 'name'));
  }

  function edit(skill, part) {
    skills = skills.map((one) => (one === skill ? { ...one, ...part } : one));
    return save();
  }

  function remove(skill) {
    skills = skills.filter((one) => one !== skill);
    return save();
  }

  /** Завести пустой навык сразу за последним навыком своей категории.
   *
   * В конец всего перечня он падать не должен: нажали в одной коробке, а
   * строка появилась бы в последней, и человек ищет её глазами по экрану.
   */
  function addSkill(category) {
    const fresh = { id: null, category, name: '', level: 5, aliases: [] };
    const last = groups.find((one) => one.name === category)?.items.at(-1);
    const at = last ? skills.indexOf(last) + 1 : skills.length;
    skills = [...skills.slice(0, at), fresh, ...skills.slice(at)];
  }

  function addCategory() {
    addSkill(NEW_CATEGORY);
  }

  /** Переименовать категорию.
   *
   * Пустое имя не отправляется, и поле возвращается к прежнему: категория
   * осталась той же, а пустое поле читалось бы как безымянная.
   *
   * Свёрнутость помнится по имени — другого ключа у категории нет, имя её и
   * определяет, — поэтому отметку перевешиваем следом. Не перевесь её, свёрнутая
   * категория раскрылась бы сама, а отметка досталась бы будущей тёзке.
   */
  function renameCategory(was, field) {
    const becomes = field.value.trim();
    if (!becomes) {
      field.value = was;
      return;
    }
    if (becomes === was) return;
    skills = skills.map((one) => (one.category === was ? { ...one, category: becomes } : one));
    if (closed.has(was)) {
      // Именно поставить, а не переключить: переименование в имя соседней
      // категории сливает их, и переключение сняло бы отметку с той, что уже
      // была свёрнута.
      const next = without(closed, was);
      next.add(becomes);
      closed = next;
    }
    return save();
  }

  function dropCategory(name) {
    leaving = null;
    skills = skills.filter((one) => one.category !== name);
    // Отметка уходит вместе с категорией: оставшись, она досталась бы
    // заведённой заново тёзке, и та открылась бы свёрнутой.
    closed = without(closed, name);
    return save();
  }

  function toggleCategory(name) {
    closed = toggled(closed, name);
  }

  $effect(() => {
    const settled = alive.mounted();
    refresh();
    return () => {
      settled();
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
        <button type="button" onclick={() => toggleCategory(group.name)}>
          <span class="material-symbols-outlined collapse-arrow">expand_more</span>
        </button>
        <input
          class="inline-edit cat-name"
          maxlength="64"
          value={group.name}
          onblur={(event) => renameCategory(group.name, event.currentTarget)}
        />
        <span class="cat-spacer"></span>
        <button class="cat-add" type="button" onclick={() => addSkill(group.name)}
          ><span class="material-symbols-outlined">add</span>Навык</button
        >
        <button
          class="cat-delete"
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

  <button class="new-box" type="button" onclick={addCategory}>+ Новая категория</button>
{/if}

{#if leaving}
  <ConfirmDialog
    message={`Удалить категорию «${leaving.name}» и все её навыки?`}
    confirmLabel="Удалить"
    onconfirm={() => dropCategory(leaving.name)}
    oncancel={() => (leaving = null)}
  />
{/if}
