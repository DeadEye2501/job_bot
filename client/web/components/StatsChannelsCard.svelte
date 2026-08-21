<script>
  // Воронка по каналам: одиннадцать колонок тремя смысловыми группами.
  //
  // Ячейки лежат в сетке поодиночке — строки как таковой нет, иначе колонки
  // соседних каналов не встали бы друг под друга. Поэтому и подсветка, и
  // нажатие висят на каждой ячейке, а роднит их номер канала.
  //
  // Колонки объявлены один раз, группами: из них собирается и шапка, и сами
  // ячейки, и ширина подписи группы, и черта между группами. Написанные порознь
  // — перечень ступеней, подписи шапки, числа сетки, — они разъезжались бы на
  // каждой правке, а видно это было бы только глазом.
  //
  // Само правило ширины живёт в оформлении, сюда уезжает одно число: встроенный
  // стиль сильнее любого селектора, и раскладку им не пишут.
  import { pressKey } from '$state/keys.js';
  import { convNote } from '$state/stats.js';

  let { channels, onpick } = $props();

  let hovered = $state(null);

  // Ступени воронки: подпись в шапке, цвет ступени и поле ответа. Цвет несёт
  // саму ступень, порядок — ход дела: от собранного к отклику и его исходу.
  // `conv` — колонка не числа, а доли: у неё своя мерка под подписью.
  const GROUPS = [
    {
      look: 'ingest',
      label: 'Ингест',
      columns: [
        { head: 'Всего', tone: '', field: 'total' },
        { head: 'Trash', tone: 'v-dim', field: 'trash' },
        { head: 'Not Fit', tone: 'v-dim', field: 'not_fit' },
        { head: 'Fit', tone: 'v-fit', field: 'fit' },
      ],
    },
    {
      look: 'funnel stats-ch-sep-l',
      label: 'Воронка отклика',
      columns: [
        { head: 'Sent', tone: 'v-sent', field: 'sent' },
        { head: 'Answ', tone: 'v-answ', field: 'answered' },
        { head: 'Invite+', tone: 'v-invite', field: 'invite_plus' },
        { head: 'Decline', tone: 'v-decline', field: 'decline' },
      ],
    },
    {
      look: 'outcome stats-ch-sep-l',
      label: 'Конверсия',
      columns: [
        { head: 'Sent → Answ', tone: 'stats-ch-conv', field: 'conv_answ_sent', conv: true },
        { head: 'Sent → Invite+', tone: 'stats-ch-conv', field: 'conv_invite_sent', conv: true },
      ],
    },
  ];

  // Черта слева отделяет группу от соседней и стоит у первой её колонки — в
  // шапке и в ячейках одинаково. Кто из колонок первая, видно из самого
  // перечня: писать это отдельной пометкой значило бы завести второго хозяина.
  const COLUMNS = GROUPS.flatMap((group) =>
    group.columns.map((column, at) => ({
      ...column,
      look: `${column.tone}${at === 0 ? ' stats-ch-sep-l' : ''}`.trim(),
      headLook: at === 0 ? 'stats-ch-sep-l' : '',
    })),
  );

  const rows = $derived(
    channels.map((one, at) => ({
      id: one.id,
      last: at === channels.length - 1,
      cells: [
        { look: 'stats-ch-name-cell', text: one.label, title: 'Открыть канал в Контактах' },
        ...COLUMNS.map((column) => ({
          look: column.look,
          text: column.conv ? '' : one[column.field],
          conv: column.conv ? convNote(one[column.field]) : null,
        })),
      ],
    })),
  );
</script>

<div class="stats-ch-grid">
  <div class="stats-ch-group"></div>
  {#each GROUPS as group (group.label)}
    <div class="stats-ch-group {group.look}" style="--cols: {group.columns.length}">
      {group.label}
    </div>
  {/each}

  <div class="stats-ch-th stats-ch-th-name">Канал</div>
  {#each COLUMNS as column (column.field)}
    <div class="stats-ch-th {column.headLook}">{column.head}</div>
  {/each}

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
        onkeydown={(event) => pressKey(event) && onpick(row.id)}
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
