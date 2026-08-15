<script>
  // Учётная запись Telegram: три поля, состояние сеанса и вход с выходом.
  //
  // Поля здесь черновые: мост принимает их только входом, а до удавшегося
  // входа они нигде не хранятся.
  import { sessionPill, sessionText } from '$state/settings.js';

  import SecretInput from './SecretInput.svelte';
  import SettingsSection from './SettingsSection.svelte';

  let { tg, draft, busy, onedit, onlogin, onlogout } = $props();
</script>

<SettingsSection icon="send" title="Telegram" pill={sessionPill(tg)}>
  <div class="settings-row">
    <input
      class="input"
      value={draft.api_id}
      placeholder="api_id"
      onblur={(event) => onedit({ api_id: event.currentTarget.value.trim() })}
    />
    <input
      class="input"
      value={draft.phone}
      placeholder="Телефон"
      onblur={(event) => onedit({ phone: event.currentTarget.value.trim() })}
    />
    <div class="span-2">
      <SecretInput
        value={draft.api_hash}
        placeholder="api_hash"
        onsave={(api_hash) => onedit({ api_hash: api_hash.trim() })}
      />
    </div>
    <div class="session-row">
      <span class="session-info">{sessionText(tg)}</span>
      <div class="session-actions">
        <button class="btn" type="button" onclick={() => onlogin()}>
          <span class="material-symbols-outlined">{tg.has_session ? 'sync' : 'login'}</span>
          {tg.has_session ? 'Перелогиниться' : 'Войти'}
        </button>
        {#if tg.has_session}
          <button class="btn danger" type="button" disabled={busy} onclick={() => onlogout()}>
            <span class="material-symbols-outlined">logout</span>
            Выйти из сессии
          </button>
        {/if}
      </div>
    </div>
  </div>
</SettingsSection>
