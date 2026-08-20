<script>
  // Окно заведения канала: одно поле, пояснение под ним и две кнопки.
  //
  // Своим окном, а не общим спрашивающим: у этого есть шапка с крестиком, свой
  // подвал и строка отказа внутри — канал заводят по нику, и ошибку в нике
  // объясняют там же, где его набирали, а не общей плашкой поверх окна.
  import ModalFoot from './ModalFoot.svelte';
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';

  let { value, trouble, saving, oninput, onadd, onclose } = $props();
</script>

<ModalShell extra="add-channel" {onclose}>
  {#snippet children()}
    <ModalHead icon="add_circle" title="Добавить канал" {onclose} />

    <div class="modal-body">
      <!-- Курсор ставится в поле сразу: окно об одном поле и открывают затем,
           чтобы в него набрать. Проверка a11y гасится нарочно — она о формах,
           где полей несколько и выбор первого за человеком. -->
      <!-- svelte-ignore a11y_autofocus -->
      <input
        class="cnt-input"
        autofocus
        maxlength="200"
        placeholder="@username канала или t.me/..."
        {value}
        oninput={(event) => oninput(event.currentTarget.value)}
        onkeydown={(event) => event.key === 'Enter' && onadd()}
      />
      <div class="cnt-add-hint">Название и аватар подгрузятся из Telegram автоматически.</div>
      {#if trouble}
        <div class="modal-error">{trouble}</div>
      {/if}
    </div>

    <ModalFoot
      label="Добавить"
      busyLabel="Добавляю…"
      busy={saving}
      ready={Boolean(value.trim())}
      oncancel={onclose}
      onconfirm={onadd}
    />
  {/snippet}
</ModalShell>
