<script>
  // Строка навыка: имя, уровень и синонимы.
  import { levelPercent } from '$state/skills.js';

  import ChipList from './ChipList.svelte';

  let { skill, onedit, onremove } = $props();

  // Число и заливка идут за пальцем, запись ждёт отпущенной кнопки: писать на
  // каждом делении значило бы десяток записей за одну протяжку, а число,
  // стоящее на месте, пока ползунок едет, читается как залипшая строка.
  let dragged = $state(null);

  const level = $derived(dragged ?? skill.level);
</script>

<div class="ruled-row skill-row">
  <input
    class="inline-edit skill-name"
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
      style="--pct: {levelPercent(level)}%"
      oninput={(event) => (dragged = Number(event.currentTarget.value))}
      onchange={(event) => {
        dragged = null;
        onedit({ level: Number(event.currentTarget.value) });
      }}
    />
    <span class="level-num">{level}/10</span>
  </div>

  <ChipList
    items={skill.aliases}
    onadd={(alias) => onedit({ aliases: [...skill.aliases, alias] })}
    onremove={(index) => onedit({ aliases: skill.aliases.filter((_, at) => at !== index) })}
  />

  <button class="icon-btn trash" type="button" title="Удалить навык" onclick={() => onremove()}>
    <span class="material-symbols-outlined">delete</span>
  </button>
</div>
