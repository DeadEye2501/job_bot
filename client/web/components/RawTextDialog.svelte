<script>
  // Исходный текст объявления — ровно то, что бот разбирал. Это не дословный
  // пост: к нему подставлены адреса спрятанных под словами ссылок и дописаны
  // статьи, на которые объявление ссылалось.
  //
  // Открывают его, когда разбор вышел кривым: по тексту видно, чего в
  // объявлении не было вовсе, а что модель прочла не так.
  import ModalKeys from './ModalKeys.svelte';

  let { id, chips, text, oncopy, onclose } = $props();
</script>

<ModalKeys close={onclose} />

<div
  class="modal-backdrop"
  role="presentation"
  onclick={(event) => event.target === event.currentTarget && onclose()}
>
  <div class="modal-dialog vac-raw-modal" role="dialog" aria-modal="true">
    <div class="modal-head">
      <span class="material-symbols-outlined">code</span>
      <div class="modal-title">
        Исходный текст вакансии
        <span class="modal-title-meta">id #{id}</span>
      </div>
      <button class="modal-close" type="button" title="Закрыть" onclick={() => onclose()}>
        <span class="material-symbols-outlined">close</span>
      </button>
    </div>

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
      <button class="raw-copy-btn" type="button" title="Скопировать" onclick={oncopy}>
        <span class="material-symbols-outlined">content_copy</span>
      </button>
      <pre class="raw-text">{text}</pre>
    </div>
  </div>
</div>
