<script>
  // Пузырь переписки: что написано, когда и дошло ли.
  //
  // Своё письмо стоит справа, чужое слева — по стороне их и различают, не читая.
  import { attachmentKind, chatTime, tick } from '$state/chat.js';

  let { message, onopen } = $props();

  const mark = $derived(tick(message));
  const attached = $derived(attachmentKind(message));
  // Непрочитанное помечено в самой разметке: к первому такому письму лента
  // прокручивается при открытии, и найти его она может только по метке.
  const unread = $derived(message.is_incoming && !message.read_at && !message.is_deleted);
</script>

<div
  class="cnt-bubble"
  class:me={!message.is_incoming}
  class:them={message.is_incoming}
  class:deleted={message.is_deleted}
  data-unread={unread ? 'true' : null}
>
  <div class="cnt-bubble-content">
    <!-- Вложение открывает система, а не страница: мост отдаёт путь к нему
         адресом `file://`, а страницу раздаёт сервер окна из своей папки —
         ссылкой такой путь не открылся бы. Файла может и не быть вовсе: бот
         скачивает не всё, — и тогда остаётся род вложения в скобках, потому что
         открывать нечего. -->
    {#if attached === 'photo'}
      <!-- Снимок виден прямо в ленте: по нему и понимают, что прислали, не
           выходя из переписки. -->
      <button class="cnt-bubble-photo" type="button" onclick={() => onopen(message)}>
        <img src={message.media_path} alt={message.media_name || 'снимок'} />
      </button>
    {:else if attached === 'file'}
      <button class="cnt-bubble-doc" type="button" onclick={() => onopen(message)}>
        <span class="material-symbols-outlined">description</span>
        <span>{message.media_name || 'документ'}</span>
      </button>
    {:else if attached === 'gone'}
      <div class="cnt-bubble-text gone">[{message.media_kind}]</div>
    {/if}

    {#if message.text || !attached}
      <div class="cnt-bubble-text" class:deleted={message.is_deleted}>
        {message.text || ''}
        {#if message.is_deleted}
          <span class="cnt-bubble-edited">(удалено)</span>
        {:else if message.is_edited}
          <span class="cnt-bubble-edited">(изм.)</span>
        {/if}
      </div>
    {/if}
  </div>

  <div class="cnt-bubble-time">
    {chatTime(message.sent_at)}
    {#if mark}<span class="cnt-bubble-tick" class:read={mark === '✓✓'}>{mark}</span>{/if}
  </div>
</div>
