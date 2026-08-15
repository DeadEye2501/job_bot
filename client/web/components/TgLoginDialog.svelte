<script>
  // Вход в Telegram: код из приложения, а следом облачный пароль, если он есть.
  //
  // Окно своё, а не общая рама вопроса: у него свой заголовок, объяснение на
  // три строки и поле ввода — оформление лежит в styles/tg-login.css.
  import ModalKeys from './ModalKeys.svelte';

  let { step, phone, relogin, busy, error, onsubmit, oncancel } = $props();

  let value = $state('');

  const asking = $derived(
    step === 'password'
      ? { placeholder: 'Облачный пароль', confirm: 'Войти', secret: true }
      : { placeholder: 'Код подтверждения', confirm: 'Подтвердить', secret: false },
  );
</script>

<!-- Escape закрывает, Enter — нет: шаг уходит только кнопкой. -->
<ModalKeys close={oncancel} />

<div class="modal-backdrop tg-login" role="presentation">
  <div class="tg-login-box" role="dialog" aria-modal="true">
    <div class="modal-title">
      <span class="material-symbols-outlined">login</span>
      {relogin ? 'Перелогиниться' : 'Войти в Telegram'}
    </div>

    {#if asking.secret}
      <div class="modal-subtitle">
        На аккаунте включена двухфакторная защита. Введите облачный пароль Telegram.
      </div>
    {:else}
      <div class="modal-subtitle">
        Код отправлен в Telegram-приложение на <strong>{phone}</strong>. Откройте Telegram и
        введите его сюда.
      </div>
    {/if}

    <!-- Фокус сразу в поле: окно открылось затем, чтобы в него набрали. -->
    <!-- svelte-ignore a11y_autofocus -->
    <input
      class="input"
      type={asking.secret ? 'password' : 'text'}
      placeholder={asking.placeholder}
      autofocus
      bind:value
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
