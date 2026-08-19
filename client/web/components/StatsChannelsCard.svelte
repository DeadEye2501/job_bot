<script>
  // Воронка по каналам: одиннадцать колонок тремя смысловыми группами.
  //
  // Ячейки лежат в сетке поодиночке — строки как таковой нет, иначе колонки
  // соседних каналов не встали бы друг под друга. Поэтому и подсветка, и
  // нажатие висят на каждой ячейке, а роднит их номер канала.
  import { convNote } from '$state/stats.js';

  let { channels, onpick } = $props();

  let hovered = $state(null);

  // Восемь ступеней воронки: чем покрашена и что показывает. Цвет несёт саму
  // ступень, и порядок здесь тот же, что в шапке.
  const STEPS = [
    { look: 'stats-ch-sep-l', field: 'total' },
    { look: 'v-dim', field: 'trash' },
    { look: 'v-dim', field: 'not_fit' },
    { look: 'v-fit', field: 'fit' },
    { look: 'v-sent stats-ch-sep-l', field: 'sent' },
    { look: 'v-answ', field: 'answered' },
    { look: 'v-invite', field: 'invite_plus' },
    { look: 'v-decline', field: 'decline' },
  ];

  const rows = $derived(
    channels.map((one, at) => ({
      id: one.id,
      last: at === channels.length - 1,
      cells: [
        { look: 'stats-ch-name-cell', text: one.label, title: 'Открыть канал в Контактах' },
        ...STEPS.map((step) => ({ look: step.look, text: one[step.field] })),
        { look: 'stats-ch-conv stats-ch-sep-l', conv: convNote(one.conv_answ_sent) },
        { look: 'stats-ch-conv', conv: convNote(one.conv_invite_sent) },
      ],
    })),
  );
</script>

<div class="stats-ch-grid">
  <div class="stats-ch-group"></div>
  <div class="stats-ch-group ingest" style="grid-column: span 4">Ингест</div>
  <div class="stats-ch-group funnel stats-ch-sep-l" style="grid-column: span 4">Воронка отклика</div>
  <div class="stats-ch-group outcome stats-ch-sep-l" style="grid-column: span 2">Конверсия</div>

  <div class="stats-ch-th stats-ch-th-name">Канал</div>
  <div class="stats-ch-th stats-ch-sep-l">Всего</div>
  <div class="stats-ch-th">Trash</div>
  <div class="stats-ch-th">Not Fit</div>
  <div class="stats-ch-th">Fit</div>
  <div class="stats-ch-th stats-ch-sep-l">Sent</div>
  <div class="stats-ch-th">Answ</div>
  <div class="stats-ch-th">Invite+</div>
  <div class="stats-ch-th">Decline</div>
  <div class="stats-ch-th stats-ch-sep-l">Sent → Answ</div>
  <div class="stats-ch-th">Sent → Invite+</div>

  {#each rows as row (row.id)}
    {#each row.cells as cell, at (at)}
      <div
        class="stats-ch-row {cell.look}"
        class:stats-ch-last={row.last}
        class:is-hover={hovered === row.id}
        role="button"
        tabindex="0"
        title={cell.title}
        onmouseenter={() => (hovered = row.id)}
        onmouseleave={() => (hovered = null)}
        onclick={() => onpick(row.id)}
        onkeydown={(event) => event.key === 'Enter' && onpick(row.id)}
      >
        {#if cell.conv}
          <span class="stats-ch-conv-label">{cell.conv.text}</span>
          <span class="stats-ch-conv-meter">
            <span class="stats-ch-conv-meter-fill" style="width: {cell.conv.percent}%"></span>
          </span>
        {:else}
          {cell.text}
        {/if}
      </div>
    {/each}
  {/each}
</div>
