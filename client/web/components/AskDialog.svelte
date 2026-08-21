<script>
  // Окно, которое что-то спрашивает: заголовок, содержимое и две кнопки.
  //
  // Общая рама для спрашивающих окон: так заводят человека и компанию — из
  // списков контактов и из карточки вакансии, где связывать оказалось не с кем.
  // Своё у каждого только то, что внутри.
  //
  // `ready` — набрано ли то, без чего заводить нечего. Пока не набрано, кнопка
  // заперта: нажавший её иначе получает плашку отказа вместо карточки, и чего
  // не хватило — узнаёт уже из неё.
  //
  // `busy` — летит ли уже ответ моста. Второе нажатие ушло бы в начатую работу
  // и завело бы вторую карточку: сторожа на одинаковое имя нет ни в базе, ни на
  // мосту, и различить их потом нечем. Подпись на это время говорит, что работа
  // идёт, — запертая кнопка без объяснения читается как поломка.
  import ModalShell from './ModalShell.svelte';

  // Содержимое переименовано при разборе доводов: внутри рамы своё место для
  // разметки тоже зовётся `children`, и одно имя закрыло бы другое.
  let {
    icon,
    title,
    subtitle = '',
    confirmLabel,
    busyLabel,
    busy,
    ready,
    onconfirm,
    oncancel,
    children: inside,
  } = $props();
</script>

<!-- Окно берёт на себя Escape, но не Enter: в нём набирают заметки в несколько
     строк, и подтверждение по Enter обрывало бы заведение на первом же
     переводе строки. -->
<ModalShell onclose={oncancel}>
  {#snippet children()}
    <div class="modal-title">
      <span class="material-symbols-outlined">{icon}</span>
      {title}
    </div>

    {#if subtitle}
      <div class="modal-subtitle">{subtitle}</div>
    {/if}

    {@render inside()}

    <div class="modal-actions">
      <button class="btn" type="button" onclick={() => oncancel()}>Отмена</button>
      <button
        class="btn primary"
        type="button"
        disabled={busy || !ready}
        onclick={() => onconfirm()}
      >
        {busy ? busyLabel : confirmLabel}
      </button>
    </div>
  {/snippet}
</ModalShell>
