<script>
  // Поставщик модели: адрес, ключ, имя модели и проверка связи.
  //
  // Секция одна на двоих — чат и эмбеддинги, — но раскладка у них разная: у
  // чата всё идёт одной сеткой, у эмбеддингов сверху стоит выбор «ходить туда
  // же, куда чат», и при нём адрес с ключом не показываются вовсе.
  import {
    CREDS_LIMITS,
    KEY_PLACEHOLDER,
    SAME_CREDS_LABEL,
    modelPlaceholder,
  } from '$state/settings.js';

  import SecretInput from './SecretInput.svelte';
  import SettingsSection from './SettingsSection.svelte';
  import SuggestInput from './SuggestInput.svelte';

  let { title, icon, creds, models, pill, busy, sameAsChat, onsave, onprobe, onsame, onedit } =
    $props();

  const embeds = $derived(sameAsChat !== undefined);
  const ownCreds = $derived(sameAsChat !== true);
  const placeholder = $derived(modelPlaceholder(models));

  /** Имя модели пришло из подсказки под полем.
   *
   * Плашка проверки гасится здесь своими руками: остальные поля гасят её
   * событием ввода, всплывающим до коробки полей, а выбор из панели такого
   * события не рождает — и плашка осталась бы говорить «отвечает» про модель,
   * которой в поле уже нет.
   */
  function keepModel(model) {
    onedit();
    return onsave({ model });
  }
</script>

{#snippet urlField(hint)}
  <input
    class="input span-2"
    maxlength={CREDS_LIMITS.base_url}
    value={creds.base_url}
    placeholder={hint}
    onblur={(event) => onsave({ base_url: event.currentTarget.value.trim() })}
  />
{/snippet}

{#snippet secretField()}
  <div class="span-2">
    <SecretInput
      value={creds.api_key || ''}
      placeholder={KEY_PLACEHOLDER}
      maxlength={CREDS_LIMITS.api_key}
      onsave={(api_key) => onsave({ api_key })}
    />
  </div>
{/snippet}

{#snippet modelField()}
  <div class="span-2">
    <SuggestInput
      value={creds.model}
      options={models}
      {placeholder}
      maxlength={CREDS_LIMITS.model}
      onsave={keepModel}
    />
  </div>
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
  <div oninput={() => onedit()}>
    {#if embeds}
      <label class="checkbox-row">
        <input
          type="checkbox"
          checked={sameAsChat}
          onchange={(event) => onsame(event.currentTarget.checked)}
        />
        {SAME_CREDS_LABEL}
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
