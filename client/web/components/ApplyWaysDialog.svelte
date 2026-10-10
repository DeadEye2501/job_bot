<script>
  // Окно выбора, куда откликнуться: строка на контакт.
  //
  // Выбор двухшаговый, как у подборщика: нажатие по строке только помечает её,
  // а отклик уходит кнопкой внизу. Ушедший отклик назад не вернуть, и промах
  // мышью не должен его отправлять.
  //
  // `locked` — чем отклик заперт сейчас; пусто — не заперт. Окно открыто до
  // обхода, а обход мог начаться, пока выбирали: подтверждение тогда заперто.
  import ModalFoot from './ModalFoot.svelte';
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';

  let { rows, locked, onapply, onclose } = $props();

  let chosen = $state(null);

  function apply() {
    const row = rows.find((one) => one.key === chosen);
    if (row !== undefined) onapply(row);
  }
</script>

<ModalShell extra="narrow apply-ways-dialog" {onclose}>
  {#snippet children()}
    <ModalHead icon="send" title="Куда откликнуться" {onclose} />

    <div class="modal-body">
      {#each rows as row (row.key)}
        <button
          class="picker-row way-row"
          class:selected={chosen === row.key}
          type="button"
          onclick={() => (chosen = row.key)}
        >
          <span class="picker-name">{row.contact}</span>
        </button>
      {/each}
    </div>

    <ModalFoot
      label="Подтвердить"
      ready={chosen !== null && !locked}
      tip={locked}
      oncancel={onclose}
      onconfirm={apply}
    />
  {/snippet}
</ModalShell>
