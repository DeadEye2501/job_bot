<script>
  // Окно выбора одной строки: куда откликнуться, какой профиль сделать
  // активным, каким способом завести новый, что сделать с файлом резюме.
  //
  // Одно на все четыре: различаются они строками и заголовком, а не окном, и
  // своё у каждого разошлось бы на первой же правке вида.
  //
  // Выбор отклика двухшаговый, как у подборщика: нажатие по строке только
  // помечает её, а дело делает кнопка внизу, — ушедший отклик назад не вернуть.
  // `instant` — строка делает дело самим нажатием, и подвала нет: промах там
  // исправим следующим же нажатием, а лишний шаг стоил бы каждого выбора.
  //
  // Строка — `{ key, label, current? }`. `current` — то, что уже есть сейчас
  // (активный профиль): выбрать его нельзя, а подписан он `mark`.
  //
  // `addLabel` и `onadd` — пунктирная кнопка «завести ещё» под строками, как
  // у навыков и мест работы. Она не строка выбора и жмётся сразу: она только
  // открывает следующее окно, и промах мышью ничего не меняет.
  //
  // `locked` — чем выбор заперт сейчас; пусто — не заперт. Окно открыто до
  // обхода, а обход мог начаться, пока выбирали. Запирает он подтверждение, а
  // без подвала — сами строки и кнопку «завести ещё».
  //
  // `slim` — окно уже обычного: у коротких строк в обычной ширине справа
  // оставалась пустая половина окна.
  import ModalFoot from './ModalFoot.svelte';
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';

  let {
    icon,
    title,
    rows,
    mark = '',
    locked,
    instant = false,
    slim = false,
    addLabel = '',
    onadd = null,
    onapply,
    onclose,
  } = $props();

  let chosen = $state(null);

  function apply() {
    const row = rows.find((one) => one.key === chosen);
    if (row !== undefined) onapply(row);
  }

  function press(row) {
    if (instant) onapply(row);
    else chosen = row.key;
  }
</script>

<ModalShell extra={slim ? 'narrow choose-dialog slim' : 'narrow choose-dialog'} {onclose}>
  {#snippet children()}
    <ModalHead {icon} {title} {onclose} />

    <div class="modal-body">
      {#each rows as row (row.key)}
        <button
          class="picker-row choose-row"
          class:selected={chosen === row.key}
          class:current={row.current}
          type="button"
          disabled={row.current || (instant && !!locked)}
          title={(instant && locked) || null}
          onclick={() => press(row)}
        >
          <span class="picker-name">
            {row.label}{#if row.current}<span class="picker-current-mark">({mark})</span>{/if}
          </span>
        </button>
      {/each}
      {#if onadd}
        <button
          class="new-box"
          type="button"
          disabled={!!locked}
          title={locked || null}
          onclick={() => onadd()}
        >
          {addLabel}
        </button>
      {/if}
    </div>

    {#if !instant}
      <ModalFoot
        label="Подтвердить"
        ready={chosen !== null && !locked}
        tip={locked}
        oncancel={onclose}
        onconfirm={apply}
      />
    {/if}
  {/snippet}
</ModalShell>
