<script>
  // Строка кандидата в окне выбора: кружок, два имени и счёт вакансий.
  //
  // Отмеченная и нынешняя различаются нарочно: первая — то, что человек выбрал
  // сейчас, вторая — то, что привязано уже, и без второй он выбрал бы того же
  // самого, не заметив.
  import { plural } from '$state/words.js';

  import Avatar from './Avatar.svelte';

  let { row, current = false, chosen = false, mark = '', onpick } = $props();

  const about = $derived(
    `${row.count} ${plural(row.count, 'вакансия', 'вакансии', 'вакансий')}`,
  );
</script>

<button
  class="picker-row"
  class:selected={chosen}
  class:current
  class:blocked={row.blocked}
  type="button"
  onclick={() => onpick(row.id)}
>
  <Avatar avatar={row.avatar} name={row.name} icon={row.icon} />
  <span class="picker-info">
    <span class="picker-name">
      {row.name}{#if current}<span class="picker-current-mark">({mark})</span>{/if}
    </span>
    <span class="picker-sub">{row.sub}</span>
  </span>
  <span class="picker-meta"><span class="vac-count" title={about}>{row.count}</span></span>
</button>
