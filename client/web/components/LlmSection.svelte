<script>
  // Поставщик модели: адрес, ключ, имя модели и проверка связи.
  //
  // Секция одна на двоих — чат и эмбеддинги, — но раскладка у них разная: у
  // чата всё идёт одной сеткой, у эмбеддингов сверху стоит выбор «ходить туда
  // же, куда чат», и при нём адрес с ключом не показываются вовсе.
  import SecretInput from './SecretInput.svelte';
  import SettingsSection from './SettingsSection.svelte';

  let { title, icon, creds, models, pill, busy, sameAsChat, onsave, onprobe, onsame, onedit } =
    $props();

  const embeds = $derived(sameAsChat !== undefined);
  const ownCreds = $derived(sameAsChat !== true);
  const placeholder = $derived(
    models.length ? 'Модель (выберите из списка или введите свою)' : 'Название модели',
  );
</script>

{#snippet urlField(hint)}
  <input
    class="input span-2"
    value={creds.base_url}
    placeholder={hint}
    onblur={(event) => onsave({ base_url: event.currentTarget.value.trim() })}
  />
{/snippet}

{#snippet secretField()}
  <div class="span-2">
    <SecretInput
      value={creds.api_key || ''}
      placeholder="api_key (оставьте пустым, если не нужен)"
      onsave={(api_key) => onsave({ api_key })}
    />
  </div>
{/snippet}

{#snippet modelField()}
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
{/snippet}

{#snippet probeButton()}
  <div class="span-2 settings-actions">
    <button class="btn" type="button" disabled={busy} onclick={() => onprobe()}>
      <span class="material-symbols-outlined">network_check</span>
      {busy ? 'Проверка…' : 'Проверить'}
    </button>
  </div>
{/snippet}

<SettingsSection {icon} {title} {pill}>
  <!-- Ввод в любое из полей гасит плашку проверки: она говорит «модель
       отвечает» про тот адрес, который проверяли, и на изменённых полях лгала
       бы. Ловится здесь, а не на каждом поле: событие всплывает, и второй
       обработчик у поля секрета пришлось бы заводить внутри чужого компонента. -->
  <div class="llm-fields" oninput={() => onedit()}>
    {#if embeds}
      <label class="checkbox-row">
        <input
          type="checkbox"
          checked={sameAsChat}
          onchange={(event) => onsame(event.currentTarget.checked)}
        />
        Использовать те же base_url и api_key, что и для чата
      </label>

      {#if ownCreds}
        <div class="settings-row spaced">
          {@render urlField('base_url')}
          {@render secretField()}
        </div>
      {/if}

      <div class="settings-row spaced">
        {@render modelField()}
        {@render probeButton()}
      </div>
    {:else}
      <div class="settings-row">
        {@render urlField('base_url (например http://localhost:1234)')}
        {@render modelField()}
        {@render secretField()}
        {@render probeButton()}
      </div>
    {/if}
  </div>
</SettingsSection>
