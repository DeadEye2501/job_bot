<script>
  // Шаг мастера: поставщик моделей — для чата или для сравнения.
  //
  // Поля голые, без коробки раздела: их три-четыре, и рамка с шапкой обещала бы
  // соседей, которых на шаге нет. Исход проверки и записи — строкой под теми же
  // полями: плашка в шапке увела бы ответ туда, куда человек в этот миг не
  // смотрит.
  //
  // Записывается шаг иначе, чем в настройках: там поле уезжает, когда его
  // покидают, здесь — по «Дальше», и только пройдя заслон. В мастере
  // недописанный адрес значил бы работающего бота без модели.
  import { call } from '$api/bridge.js';
  import { mirrored, sameCreds } from '$state/settings.js';
  import WizardFoot from '$components/WizardFoot.svelte';
  import { PRESETS, llmTrouble, presetFor } from '$state/wizard.js';

  // Значок строки состояния: чем шаг занят и чем кончилось.
  const TONE_ICONS = { busy: 'progress_activity', ok: 'check_circle', err: 'error' };

  let { ask, kind, onback, onnext } = $props();

  let creds = $state({ base_url: '', api_key: '', model: '' });
  let chat = $state({ base_url: '', api_key: '', model: '' });
  let sameAsChat = $state(true);
  let models = $state([]);
  let status = $state(null);
  let shownKey = $state(false);
  let busy = $state(false);

  let alive = true;

  const chatStep = $derived(kind === 'chat');
  // Адрес и ключ стоят только там, где их набирают: при отмеченной галочке они
  // те же, что у чата, и показывать их значило бы предлагать править то, что
  // тут же перепишется чатовым.
  const ownCreds = $derived(chatStep || !sameAsChat);
  const namePlaceholder = $derived(
    models.length ? 'Модель (выберите из списка или введите свою)' : 'Название модели',
  );
  // Незнакомый адрес отмечен как «своё»: пустая отметка читалась бы как
  // «поставщик не выбран», хотя адрес уже вписан.
  const chosenPreset = $derived(presetFor(creds.base_url));

  async function refresh() {
    const now = await ask('settings.get');
    if (now === null || !alive) return;
    chat = now.chat;
    if (chatStep) {
      creds = now.chat;
    } else {
      // Эмбеддинги начинают с того же адреса и ключа, что и чат: шаг о том и
      // говорит, а пустые поля заставляли бы перенабирать ключ вслепую. Своими
      // они считаются, только если своими и записаны.
      sameAsChat = now.embed.base_url ? sameCreds(now.chat, now.embed) : true;
      creds = sameAsChat ? mirrored(now.chat, now.embed) : now.embed;
    }
    return listModels();
  }

  /** Спросить у поставщика имена его моделей. Ничего — это отказ моста. */
  async function listModels() {
    const answer = await ask('settings.list_models', {
      kind,
      base_url: creds.base_url,
      api_key: creds.api_key,
    });
    if (answer === null || !alive) return null;
    models = answer.models || [];
    return models;
  }

  /** Поправить поле.
   *
   * Перечень имён спрашивается заново на смене адреса или ключа: он с них и
   * читается, и оставленный прежним подсказывал бы модели чужого сервера.
   */
  function edit(part) {
    creds = { ...creds, ...part };
    // Строка состояния говорит про те данные, которые проверяли: правь их — ей
    // верить больше нельзя.
    status = null;
    if (part.base_url !== undefined || part.api_key !== undefined) return listModels();
  }

  /** Выбрать готового поставщика: адрес подставляется, имя модели сбрасывается.
   *
   * Набранное для прежнего поставщика у нового почти наверняка не заведётся, и
   * оставленное имя ушло бы в проверку молчаливой ошибкой.
   */
  function pickPreset(label) {
    const preset = PRESETS.find((one) => one.label === label);
    if (preset === undefined) return;
    return edit({ base_url: preset.base_url, model: '' });
  }

  /** Переключить эмбеддинги на чатовые адрес и ключ — или на свои. */
  function useChatCreds(on) {
    sameAsChat = on;
    status = null;
    if (on) creds = mirrored(chat, creds);
    return listModels();
  }

  /** Проверить связь с поставщиком.
   *
   * Мосту едут набранные данные, а не сохранённые: в мастере сохранённых ещё
   * нет вовсе, и проверять было бы нечего.
   *
   * Без имени модели проверять нечего, и нажатие работает как «спросить имена у
   * поставщика»: у местных заранее не выписано ни одного, и до этого спроса
   * подсказка поля пуста.
   */
  async function check() {
    if (busy) return;
    if (!creds.base_url.trim()) {
      status = { tone: 'err', text: 'Укажите base_url провайдера.' };
      return;
    }
    busy = true;
    if (!creds.model.trim()) {
      status = { tone: 'busy', text: 'Загружаем список моделей у провайдера...' };
      const found = await listModels();
      if (!alive) return;
      busy = false;
      if (found === null) {
        status = { tone: 'err', text: 'Не удалось получить список моделей.' };
      } else if (!found.length) {
        status = {
          tone: 'err',
          text: 'Провайдер не вернул ни одной модели — проверьте, что в LM Studio загружена модель.',
        };
      } else {
        status = {
          tone: 'ok',
          text: `Найдено моделей: ${found.length}. Выберите модель из списка и нажмите «Проверить».`,
        };
      }
      return;
    }
    status = { tone: 'busy', text: 'Проверяем подключение...' };
    let answer = null;
    let refused = '';
    try {
      // Зовём мост напрямую: отказ поставщика — это и есть исход проверки, и
      // человек читает его строкой под тем самым полем.
      answer = await call('settings.probe_model', { kind, ...creds });
    } catch (refusal) {
      refused = refusal.message;
    }
    if (!alive) return;
    busy = false;
    // Поля могли поправить, пока ответ шёл: исход говорил бы про данные,
    // которых в них уже нет.
    if (status?.tone !== 'busy') return;
    status =
      answer === null
        ? { tone: 'err', text: refused }
        : {
            tone: 'ok',
            text: `Подключение работает (${answer.model} · ${answer.latency_ms}ms)`,
          };
  }

  async function save() {
    if (busy) return;
    const trouble = llmTrouble(creds);
    if (trouble) {
      status = { tone: 'err', text: trouble };
      return;
    }
    busy = true;
    status = { tone: 'busy', text: 'Сохраняем...' };
    // Адрес уезжает обрезанным: заслон судит по обрезанному, и пробел на конце
    // прошёл бы проверку, а на мост уехал бы вместе с ним.
    creds = ownCreds ? { ...creds, base_url: creds.base_url.trim() } : mirrored(chat, creds);
    try {
      // Зовём мост напрямую: отказ записи — исход шага, и читают его там же,
      // где исход проверки.
      await call('settings.save', chatStep ? { chat: creds } : { embed: creds });
    } catch (refusal) {
      if (!alive) return;
      busy = false;
      status = { tone: 'err', text: refusal.message };
      return;
    }
    if (!alive) return;
    busy = false;
    return onnext();
  }

  $effect(() => {
    alive = true;
    refresh();
    return () => {
      alive = false;
    };
  });
</script>

<div class="wiz-body">
  <div class="wiz-title">{chatStep ? 'LLM для чата' : 'LLM для эмбеддингов'}</div>

  {#if chatStep}
    <div class="wiz-subtitle">
      На этой модели бот <strong>разбирает вакансии</strong> и классифицирует ответы HR. Подойдёт
      любой сервис с OpenAI-совместимым API.
    </div>
  {:else}
    <div class="wiz-subtitle">
      Эмбеддинг — числовое представление текста. Бот превращает в эмбеддинги каждую вакансию и ваш
      профиль и сравнивает их между собой — так он понимает, насколько вакансия вам подходит. Без
      этого бот не сможет ставить вакансиям оценки и отсеивать повторы из разных каналов.
    </div>
    <div class="info-card">
      <span class="material-symbols-outlined">info</span>
      <div>
        Embedding-модель — отдельная от чат-модели. У облачных провайдеров
        (<strong>OpenAI</strong>, <strong>OpenRouter</strong>) тот же ключ обычно открывает доступ
        и к ней — оставьте галочку ниже. У локальных (<strong>LM Studio</strong>,
        <strong>Ollama</strong>) embedding-модель нужно загрузить отдельно — это другая модель, не
        та, что вы используете для чата.
      </div>
    </div>
  {/if}

  <div class="wiz-fields">
    {#if chatStep}
      <select
        class="preset-select"
        value={chosenPreset}
        onchange={(event) => pickPreset(event.currentTarget.value)}
      >
        {#each PRESETS as one (one.label)}
          <option value={one.label}>{one.label}</option>
        {/each}
      </select>
    {:else}
      <label class="checkbox-row">
        <input
          type="checkbox"
          checked={sameAsChat}
          onchange={(event) => useChatCreds(event.currentTarget.checked)}
        />
        Те же base_url и api_key, что и для чата
      </label>
    {/if}

    {#if ownCreds}
      <input
        class="input mono"
        maxlength="255"
        placeholder="base_url"
        value={creds.base_url}
        onblur={(event) => edit({ base_url: event.currentTarget.value.trim() })}
      />
      <div class="secret-input">
        <input
          class="input mono"
          type={shownKey ? 'text' : 'password'}
          maxlength="512"
          placeholder="api_key (если требуется)"
          value={creds.api_key}
          onblur={(event) => edit({ api_key: event.currentTarget.value })}
        />
        <button
          class="icon-btn"
          type="button"
          title={shownKey ? 'Скрыть' : 'Показать'}
          onclick={() => (shownKey = !shownKey)}
        >
          <span class="material-symbols-outlined">
            {shownKey ? 'visibility_off' : 'visibility'}
          </span>
        </button>
      </div>
    {/if}

    <input
      class="input mono"
      list="{kind}-model-presets"
      autocomplete="off"
      maxlength="128"
      placeholder={namePlaceholder}
      value={creds.model}
      onblur={(event) => edit({ model: event.currentTarget.value.trim() })}
    />
    <datalist id="{kind}-model-presets">
      {#each models as one (one)}
        <option value={one}></option>
      {/each}
    </datalist>

    <div class="help">
      После «Проверить» список заменится теми моделями, которые реально доступны у провайдера.
    </div>

    {#if status}
      <div class="status-row" data-tone={status.tone}>
        <span class="material-symbols-outlined">{TONE_ICONS[status.tone]}</span>
        <span>{status.text}</span>
      </div>
    {/if}
  </div>

  {#if chatStep}
    <div class="info-card">
      <span class="material-symbols-outlined">privacy_tip</span>
      <div>
        <strong>Что уходит провайдеру.</strong> Тексты вакансий, ваше резюме и переписка с HR будут
        отправляться выбранной модели. Для полной приватности подключите локальный
        <strong>LM Studio</strong> или <strong>Ollama</strong>.
      </div>
    </div>
  {/if}
</div>

<WizardFoot nextLabel="Дальше" nextIcon="arrow_forward" {busy} {onback} onnext={save}>
  {#snippet children()}
    <button class="btn" type="button" disabled={busy} onclick={check}>
      <span class="material-symbols-outlined">network_check</span>Проверить
    </button>
  {/snippet}
</WizardFoot>
