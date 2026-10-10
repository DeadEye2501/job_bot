<script>
  // Почта для откликов письмом: адрес, пароль приложения и — только для
  // незнакомой почты — сервер с портом.
  //
  // Пароль приходит открытым, как ключи моделей: подключённая почта открывается
  // с ним точками, и глазом его можно показать. Уходит он, только если сменился.
  import { mailNeedsServer, mailPill } from '$state/settings.js';

  import MailPasswordHelp from './MailPasswordHelp.svelte';
  import SecretInput from './SecretInput.svelte';
  import SettingsSection from './SettingsSection.svelte';

  let { mail, onsave, onopen } = $props();

  let helping = $state(false);
</script>

<SettingsSection icon="mail" title="Почта" pill={mailPill(mail)}>
  <div class="settings-row">
    <input
      class="input"
      value={mail.address ?? ''}
      placeholder="Адрес почты"
      onblur={(event) => onsave({ address: event.currentTarget.value.trim() })}
    />
    <SecretInput
      value={mail.password ?? ''}
      placeholder="Пароль приложения"
      onsave={(password) => password !== (mail.password ?? '') && onsave({ password })}
      onhelp={() => (helping = true)}
    />
    {#if mailNeedsServer(mail)}
      <input
        class="input"
        value={mail.smtp_host ?? ''}
        placeholder="SMTP-сервер"
        onblur={(event) => onsave({ smtp_host: event.currentTarget.value.trim() || null })}
      />
      <input
        class="input"
        type="number"
        value={mail.smtp_port ?? ''}
        placeholder="Порт"
        onblur={(event) => onsave({ smtp_port: Number.parseInt(event.currentTarget.value, 10) || null })}
      />
    {/if}
  </div>
</SettingsSection>

{#if helping}
  <MailPasswordHelp {onopen} onclose={() => (helping = false)} />
{/if}
