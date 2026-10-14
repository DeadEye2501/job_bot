<script>
  // Вход в Telegram: код из приложения, а следом облачный пароль, если он есть.
  //
  // Рама, шапка, тело и подвал — общие окна (`narrow`); своё у окна только
  // место в стопке (styles/tg-login.css). Нажатием по затемнению оно не
  // закрывается: код набирают в чужом приложении, и промах мимо коробки стоил
  // бы нового кода.
  import ModalFoot from './ModalFoot.svelte';
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';
  import SecretInput from './SecretInput.svelte';

  let { step, phone, relogin, busy, error, onsubmit, oncancel } = $props();

  let value = $state('');

  const asking = $derived(
    step === 'password'
      ? { placeholder: 'Облачный пароль', confirm: 'Войти', secret: true }
      : { placeholder: 'Код подтверждения', confirm: 'Подтвердить', secret: false },
  );
</script>

<!-- Escape закрывает, Enter — нет: шаг уходит только кнопкой. -->
<ModalShell extra="narrow" over="tg-login" awayCloses={false} onclose={oncancel}>
  {#snippet children()}
    <ModalHead icon="login" title={relogin ? 'Перелогиниться' : 'Войти в Telegram'} />

    <div class="modal-body">
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

      <!-- Фокус сразу в поле: окно открылось затем, чтобы в него набрали. Пароль
           — полем секрета с глазом; набранное уходит при уходе из поля, а уходят
           из него раньше, чем засчитывается нажатие «Войти». -->
      {#if asking.secret}
        <SecretInput {value} placeholder={asking.placeholder} autofocus onsave={(typed) => (value = typed)} />
      {:else}
        <!-- svelte-ignore a11y_autofocus -->
        <input class="input" placeholder={asking.placeholder} autofocus bind:value />
      {/if}

      {#if error}
        <div class="modal-error">{error}</div>
      {/if}
    </div>

    <ModalFoot
      label={asking.confirm}
      busyLabel="Проверка…"
      {busy}
      {oncancel}
      onconfirm={() => onsubmit(value)}
    />
  {/snippet}
</ModalShell>
