<script>
  // Поставщик модели: адрес, ключ, имя модели и проверка связи.
  //
  // Секция одна на двоих — чат и эмбеддинги, — и различаются они только тем,
  // что у эмбеддингов есть выбор «ходить туда же, куда чат»: при нём поля
  // адреса и ключа не показываются вовсе, они копируются с чата.
  import SecretInput from './SecretInput.svelte';
  import SettingsSection from './SettingsSection.svelte';

  let { title, icon, creds, models, pill, busy, sameAsChat, onsave, onprobe, onsame } = $props();

  const ownCreds = $derived(sameAsChat !== true);
  const placeholder = $derived(
    models.length ? 'Модель (выберите из списка или введите свою)' : 'Название модели',
  );
</script>

<SettingsSection {icon} {title} {pill}>
  {#if sameAsChat !== undefined}
    <label class="checkbox-row">
      <input
        type="checkbox"
        checked={sameAsChat}
        onchange={(event) => onsame(event.currentTarget.checked)}
      />
      Использовать те же base_url и api_key, что и для чата
    </label>
  {/if}

  <div class="settings-row">
    {#if ownCreds}
      <input
        class="input span-2"
        value={creds.base_url}
        placeholder="base_url (например http://localhost:1234)"
        onblur={(event) => onsave({ base_url: event.currentTarget.value.trim() })}
      />
      <div class="span-2">
        <SecretInput
          value={creds.api_key || ''}
          placeholder="api_key (оставьте пустым, если не нужен)"
          onsave={(api_key) => onsave({ api_key })}
        />
      </div>
    {/if}

    <input
      class="input span-2"
      list="{icon}-models"
      autocomplete="off"
      value={creds.model}
      {placeholder}
      onblur={(event) => onsave({ model: event.currentTarget.value.trim() })}
    />
    <datalist id="{icon}-models">
      {#each models as one (one)}
        <option value={one}></option>
      {/each}
    </datalist>

    <div class="span-2 settings-actions">
      <button class="btn" type="button" disabled={busy} onclick={() => onprobe()}>
        <span class="material-symbols-outlined">network_check</span>
        {busy ? 'Проверка…' : 'Проверить'}
      </button>
    </div>
  </div>
</SettingsSection>
