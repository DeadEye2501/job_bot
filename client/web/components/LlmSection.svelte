<script>
  // Поставщик модели: адрес, ключ, имя модели и проверка связи.
  //
  // Секция одна на двоих — чат и эмбеддинги, — но раскладка у них разная. У
  // чата сверху выбор поставщика, и у Claude Code адреса с ключом нет вовсе. У
  // эмбеддингов сверху выбор «сервер или файл модели»; у сервера — галочка
  // «ходить туда же, куда чат», и при ней адрес с ключом не показываются.
  import {
    CREDS_LIMITS,
    EMBED_SOURCES,
    KEY_PLACEHOLDER,
    PRESET_NAMES,
    SAME_CREDS_LABEL,
    addressless,
    modelPlaceholder,
    presetFor,
  } from '$state/settings.js';

  import Dropdown from './Dropdown.svelte';
  import SecretInput from './SecretInput.svelte';
  import SettingsSection from './SettingsSection.svelte';
  import SuggestInput from './SuggestInput.svelte';

  let {
    title,
    icon,
    creds,
    models,
    pill,
    busy,
    sameAsChat,
    shareable = true,
    fromFile = false,
    onsave,
    onprobe,
    onsame,
    onedit,
    onpreset,
    onsource,
    onpickfile,
  } = $props();

  const embeds = $derived(sameAsChat !== undefined);
  const ownCreds = $derived(!shareable || sameAsChat !== true);
  const placeholder = $derived(modelPlaceholder(models));
  // Незнакомый адрес отмечен как «своё»: пустая отметка читалась бы как
  // «поставщик не выбран», хотя адрес уже вписан.
  const chosenPreset = $derived(presetFor(creds.base_url));

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
    {#if fromFile}
      <button class="btn" type="button" disabled={busy} onclick={() => onpickfile()}>
        <span class="material-symbols-outlined">folder_open</span>
        Выбрать файл
      </button>
    {/if}
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
      <div class="settings-row spaced">
        <div class="span-2">
          <Dropdown
            options={EMBED_SOURCES}
            value={fromFile ? EMBED_SOURCES[1] : EMBED_SOURCES[0]}
            onpick={(source) => onsource(source === EMBED_SOURCES[1])}
          />
        </div>
      </div>

      {#if fromFile}
        <div class="settings-row spaced">
          <input
            class="input mono span-2"
            readonly
            value={creds.model}
            title={creds.model}
            placeholder="Файл модели не выбран"
          />
          {@render probeButton()}
        </div>
      {:else}
        {#if shareable}
          <label class="checkbox-row">
            <input
              type="checkbox"
              checked={sameAsChat}
              onchange={(event) => onsame(event.currentTarget.checked)}
            />
            {SAME_CREDS_LABEL}
          </label>
        {/if}

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
      {/if}
    {:else}
      <div class="settings-row">
        <div class="span-2">
          <Dropdown options={PRESET_NAMES} value={chosenPreset} onpick={onpreset} />
        </div>
        {#if !addressless(creds.base_url)}
          {@render urlField('base_url (например http://localhost:1234)')}
        {/if}
        {@render modelField()}
        {#if !addressless(creds.base_url)}
          {@render secretField()}
        {/if}
        {@render probeButton()}
      </div>
    {/if}
  </div>
</SettingsSection>
