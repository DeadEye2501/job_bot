<script>
  // Пузырь переписки: что написано, когда и дошло ли.
  //
  // Своё письмо стоит справа, чужое слева — по стороне их и различают, не читая.
  import { chatTime, tick } from '$state/chat.js';

  let { message, onopen } = $props();

  const mark = $derived(tick(message));
</script>

<div class="bubble" class:mine={!message.is_incoming} class:dropped={message.is_deleted}>
  <div class="bubble-body">
    <!-- Вложение открывает система, а не страница: мост отдаёт путь к нему
         адресом `file://`, а страницу раздаёт сервер окна из своей папки —
         ссылкой такой путь не открылся бы. Файла может и не быть вовсе: бот
         скачивает не всё, — и тогда остаётся имя без нажатия, потому что
         открывать нечего. -->
    {#if message.media_kind && message.media_path}
      <button class="bubble-file" type="button" onclick={() => onopen(message)}>
        <span class="material-symbols-outlined">attach_file</span>
        <span>{message.media_name || 'вложение'}</span>
      </button>
    {:else if message.media_kind}
      <span class="bubble-file missing">
        <span class="material-symbols-outlined">attach_file</span>
        <span>{message.media_name || 'вложение'} — файла нет на диске</span>
      </span>
    {/if}

    {#if message.text}<span class="bubble-text">{message.text}</span>{/if}
    {#if message.is_deleted}
      <span class="bubble-mark">(удалено)</span>
    {:else if message.is_edited}
      <span class="bubble-mark">(изменено)</span>
    {/if}
  </div>

  <div class="bubble-time">
    {chatTime(message.sent_at)}
    {#if mark}<span class="bubble-tick" data-tick={mark}>{mark}</span>{/if}
  </div>
</div>
