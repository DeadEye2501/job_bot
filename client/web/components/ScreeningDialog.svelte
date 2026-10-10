<script>
  // Скрининг по вакансии диалогом: отклик за откликом, реплики по порядку.
  //
  // Лента, пузыри и пилюля-разделитель — те же, что в переписке с HR
  // (`chat.css`): наше справа, работодателя слева, адрес отклика делит ленту
  // поперёк, как день в переписке. Отметок времени и прочтения
  // нет: реплики пишет агент разом, по окончании отклика.
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';

  let { applications, onclose } = $props();
</script>

<ModalShell extra="narrow roomy" {onclose}>
  {#snippet children()}
    <ModalHead icon="forum" title="Скрининг" {onclose} />

    <div class="modal-body cnt-chat-body">
      {#each applications as one, at (at)}
        <div class="cnt-chat-day">{one.target}</div>
        {#each one.lines as line, place (place)}
          <div class="cnt-bubble" class:me={line.from_us} class:them={!line.from_us}>
            <div class="cnt-bubble-content">
              <div class="cnt-bubble-text">{line.text}</div>
            </div>
          </div>
        {/each}
      {/each}
    </div>
  {/snippet}
</ModalShell>
