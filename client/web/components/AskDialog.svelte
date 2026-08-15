<script>
  // Окно, которое что-то спрашивает: заголовок, содержимое и две кнопки.
  //
  // Общая рама для спрашивающих окон — заведение канала, заведение строки
  // отсева. Своё у каждого только то, что внутри.
  import ModalKeys from './ModalKeys.svelte';

  let { icon, title, subtitle = '', confirmLabel, onconfirm, oncancel, children } = $props();
</script>

<!-- Окно берёт на себя Escape, но не Enter: в нём набирают заметки в несколько
     строк, и подтверждение по Enter обрывало бы заведение на первом же
     переводе строки. -->
<ModalKeys close={oncancel} />

<div
  class="modal-backdrop"
  role="presentation"
  onclick={(event) => event.target === event.currentTarget && oncancel()}
>
  <div class="modal-dialog" role="dialog" aria-modal="true">
    <div class="modal-title">
      <span class="material-symbols-outlined">{icon}</span>
      {title}
    </div>

    {#if subtitle}
      <div class="modal-subtitle">{subtitle}</div>
    {/if}

    {@render children()}

    <div class="modal-actions">
      <button class="btn" type="button" onclick={() => oncancel()}>Отмена</button>
      <button class="btn primary" type="button" onclick={() => onconfirm()}>{confirmLabel}</button>
    </div>
  </div>
</div>
