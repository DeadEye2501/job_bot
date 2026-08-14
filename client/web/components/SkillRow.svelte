<script>
  // Строка навыка: имя, уровень и синонимы.
  import { levelPercent } from '$state/skills.js';

  import ChipList from './ChipList.svelte';

  let { skill, onedit, onremove } = $props();
</script>

<div class="skill-row">
  <input
    class="input skill-name"
    maxlength="64"
    value={skill.name}
    onblur={(event) => onedit({ name: event.currentTarget.value.trim() })}
  />

  <div class="level">
    <input
      type="range"
      class="slider"
      min="1"
      max="10"
      value={skill.level}
      style="--pct: {levelPercent(skill.level)}%"
      onchange={(event) => onedit({ level: Number(event.currentTarget.value) })}
    />
    <span class="level-num">{skill.level}/10</span>
  </div>

  <ChipList
    items={skill.aliases}
    onadd={(alias) => onedit({ aliases: [...skill.aliases, alias] })}
    onremove={(index) => onedit({ aliases: skill.aliases.filter((_, at) => at !== index) })}
  />

  <button class="icon-btn" type="button" title="Удалить навык" onclick={() => onremove()}>
    <span class="material-symbols-outlined">delete</span>
  </button>
</div>
