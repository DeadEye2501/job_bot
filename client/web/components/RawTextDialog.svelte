<script>
  // Исходный текст объявления — ровно то, что бот разбирал. Это не дословный
  // пост: к нему подставлены адреса спрятанных под словами ссылок и дописаны
  // статьи, на которые объявление ссылалось.
  //
  // Открывают его, когда разбор вышел кривым: по тексту видно, чего в
  // объявлении не было вовсе, а что модель прочла не так.
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';

  let { id, chips, text, oncopy, onclose } = $props();
</script>

<ModalShell extra="vac-raw-modal" {onclose}>
  {#snippet children()}
    <ModalHead icon="code" title="Исходный текст вакансии" meta="id #{id}" {onclose} />

    <div class="raw-meta">
      {#each chips as chip (chip.icon)}
        <span class="raw-meta-chip">
          <span class="material-symbols-outlined">{chip.icon}</span>{chip.text}
        </span>
      {/each}
    </div>

    <div class="modal-body">
      <!-- Кнопка стоит поверх текста и полупрозрачна: окно узкое, и вынесенная
           в подвал она отняла бы у текста строку ради того, что нажимают раз в
           десять открытий. -->
      <button class="icon-btn raw-copy-btn" type="button" title="Скопировать" onclick={oncopy}>
        <span class="material-symbols-outlined">content_copy</span>
      </button>
      <pre class="raw-text">{text}</pre>
    </div>
  {/snippet}
</ModalShell>
