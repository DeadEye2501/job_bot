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
  import { living } from '$state/alive.js';
  import { askModels, probeModel } from '$state/provider.js';
  import {
    CREDS_LIMITS,
    blankCreds,
    KEY_PLACEHOLDER,
    SAME_CREDS_LABEL,
    mirrored,
    modelPlaceholder,
    sameCreds,
  } from '$state/settings.js';
  import Dropdown from '$components/Dropdown.svelte';
  import SecretInput from '$components/SecretInput.svelte';
  import SuggestInput from '$components/SuggestInput.svelte';
  import WizardFoot from '$components/WizardFoot.svelte';
  import WizardStatus from '$components/WizardStatus.svelte';
  import { PRESETS, llmTrouble, presetFor } from '$state/wizard.js';

  // Список выбирают по имени поставщика, адрес за именем ищет `presetFor`.
  const PRESET_NAMES = PRESETS.map((one) => one.label);

  let { ask, kind, onback, onnext } = $props();

  let creds = $state(blankCreds());
  let chat = $state(blankCreds());
  let sameAsChat = $state(true);
  let models = $state([]);
  let status = $state(null);
  let busy = $state(false);

  const alive = living();

  const chatStep = $derived(kind === 'chat');
  // Адрес и ключ стоят только там, где их набирают: при отмеченной галочке они
  // те же, что у чата, и показывать их значило бы предлагать править то, что
  // тут же перепишется чатовым.
  const ownCreds = $derived(chatStep || !sameAsChat);
  const namePlaceholder = $derived(modelPlaceholder(models));
  // Незнакомый адрес отмечен как «своё»: пустая отметка читалась бы как
  // «поставщик не выбран», хотя адрес уже вписан.
  const chosenPreset = $derived(presetFor(creds.base_url));

  async function refresh() {
    const now = await ask('settings.get');
    if (now === null || !alive.now) return;
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

  /** Спросить у поставщика имена его моделей.
   *
   * Молча: перечень — подсказка к полю, а не действие человека. Спрашивается он
   * на каждую правку адреса и ключа, и непóднятый поставщик отвечает отказом на
   * каждый знак — плашка беды выскакивала бы поверх набора. Не ответил — список
   * пуст, имя модели вписывают руками.
   *
   * Отказ при этом не теряется, а возвращается фразой: по нажатию «Проверить»
   * его и показывают, и путать его с пустым перечнем нельзя — «сервер молчит» и
   * «в сервере нет моделей» чинятся по-разному.
   */
  async function listModels() {
    const found = await askModels(call, { kind, ...creds });
    if (!alive.now) return found;
    models = found.models;
    return found;
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
    if (creds.model.trim()) await probe();
    else await askNames();
    if (alive.now) busy = false;
  }

  /** Спросить у поставщика перечень его моделей.
   *
   * Три исхода, и они разные: сервер не отозвался, сервер поднят и пуст, сервер
   * назвал имена. Первые два человек чинит по-разному — одно поднятием
   * сервера, другое загрузкой модели в него.
   */
  async function askNames() {
    status = { tone: 'busy', text: 'Загружаем список моделей у провайдера...' };
    const found = await listModels();
    if (!alive.now) return;
    if (found.trouble) {
      status = { tone: 'err', text: found.trouble };
      return;
    }
    if (!found.models.length) {
      status = {
        tone: 'err',
        text: 'Провайдер не вернул ни одной модели — проверьте, что в LM Studio загружена модель.',
      };
      return;
    }
    status = {
      tone: 'ok',
      text: `Найдено моделей: ${found.models.length}. Выберите модель из списка и нажмите «Проверить».`,
    };
  }

  /** Проверить связь с поставщиком: имя модели набрано, и спрашивать есть что. */
  async function probe() {
    status = { tone: 'busy', text: 'Проверяем подключение...' };
    const done = await probeModel(call, { kind, ...creds });
    if (!alive.now) return;
    // Поля могли поправить, пока ответ шёл: исход говорил бы про данные,
    // которых в них уже нет.
    if (status?.tone !== 'busy') return;
    status = done.ok
      ? { tone: 'ok', text: `Подключение работает (${done.model} · ${done.latencyMs}ms)` }
      : { tone: 'err', text: done.trouble };
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
      // где исход проверки, — строкой под полями.
      await call('settings.save', chatStep ? { chat: creds } : { embed: creds });
    } catch (refusal) {
      if (!alive.now) return;
      busy = false;
      status = { tone: 'err', text: refusal.message };
      return;
    }
    if (!alive.now) return;
    busy = false;
    return onnext();
  }

  $effect(() => {
    return alive.entered(refresh);
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
      <Dropdown options={PRESET_NAMES} value={chosenPreset} onpick={pickPreset} />
    {:else}
      <label class="checkbox-row">
        <input
          type="checkbox"
          checked={sameAsChat}
          onchange={(event) => useChatCreds(event.currentTarget.checked)}
        />
        {SAME_CREDS_LABEL}
      </label>
    {/if}

    {#if ownCreds}
      <input
        class="input mono"
        maxlength={CREDS_LIMITS.base_url}
        placeholder="base_url"
        value={creds.base_url}
        onblur={(event) => edit({ base_url: event.currentTarget.value.trim() })}
      />
      <SecretInput
        value={creds.api_key}
        placeholder={KEY_PLACEHOLDER}
        mono
        maxlength={CREDS_LIMITS.api_key}
        onsave={(api_key) => edit({ api_key })}
      />
    {/if}

    <SuggestInput
      value={creds.model}
      options={models}
      placeholder={namePlaceholder}
      mono
      maxlength={CREDS_LIMITS.model}
      onsave={(model) => edit({ model })}
    />

    <div class="help">
      После «Проверить» список заменится теми моделями, которые реально доступны у провайдера.
    </div>

    <WizardStatus {status} />
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
