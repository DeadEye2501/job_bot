<script>
  // Вход в Telegram: код из приложения, а следом облачный пароль, если он есть.
  let { step, phone, busy, error, onsubmit, oncancel } = $props();

  let value = $state('');

  const asking = $derived(
    step === 'password'
      ? {
          title: 'На аккаунте включена двухфакторная защита. Введите облачный пароль Telegram.',
          placeholder: 'Облачный пароль',
          confirm: 'Войти',
          secret: true,
        }
      : {
          title: `Код отправлен в Telegram-приложение на ${phone}. Откройте Telegram и введите его сюда.`,
          placeholder: 'Код подтверждения',
          confirm: 'Подтвердить',
          secret: false,
        },
  );
</script>

<div class="modal-backdrop" role="presentation">
  <div class="modal-dialog" role="dialog" aria-modal="true">
    <div class="modal-title">
      <span class="material-symbols-outlined">login</span>
      Вход в Telegram
    </div>

    <div class="modal-subtitle">{asking.title}</div>

    <input
      class="input"
      type={asking.secret ? 'password' : 'text'}
      placeholder={asking.placeholder}
      bind:value
      onkeydown={(event) => event.key === 'Enter' && !busy && onsubmit(value)}
    />

    {#if error}
      <div class="modal-error">{error}</div>
    {/if}

    <div class="modal-actions">
      <button class="btn" type="button" onclick={() => oncancel()}>Отмена</button>
      <button class="btn primary" type="button" disabled={busy} onclick={() => onsubmit(value)}>
        {busy ? 'Проверка…' : asking.confirm}
      </button>
    </div>
  </div>
</div>
