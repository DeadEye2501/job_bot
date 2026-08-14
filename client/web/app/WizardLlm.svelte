<script>
  // Шаг мастера: поставщик моделей — для чата или для сравнения.
  //
  // Раздел тот же, что и в настройках, а записывается иначе: там поле уезжает,
  // когда его покидают, здесь — по «Дальше», и только пройдя заслон. В мастере
  // недописанный адрес значил бы работающего бота без модели.
  import { call } from '$api/bridge.js';
  import ChoiceRow from '$components/ChoiceRow.svelte';
  import LlmSection from '$components/LlmSection.svelte';
  import WizardFoot from '$components/WizardFoot.svelte';
  import { idleProbe, mirrored, probePill } from '$state/settings.js';
  import { PRESETS, llmTrouble } from '$state/wizard.js';

  let { ask, kind, icon, title, onback, onnext } = $props();

  let creds = $state({ base_url: '', api_key: '', model: '' });
  let models = $state([]);
  let probe = $state(idleProbe());
  let saving = $state(false);

  let alive = true;

  const pill = $derived(probePill(probe));
  const trouble = $derived(llmTrouble(creds));
  // Готовый поставщик отмечен, пока адрес его: набранный руками не совпадает ни
  // с одним, и отмеченным не остаётся ни один — это и значит «своё».
  const chosenPreset = $derived(
    PRESETS.find((one) => one.base_url === creds.base_url.trim())?.label ?? '',
  );

  async function refresh() {
    const now = await ask('settings.get');
    if (now === null || !alive) return;
    // Эмбеддинги начинают с того же адреса и ключа, что и чат: шаг о том и
    // говорит, а пустые поля заставляли бы перенабирать ключ вслепую.
    creds = kind === 'chat' ? now.chat : mirrored(now.chat, now.embed);
    return listModels();
  }

  async function listModels() {
    const answer = await ask('settings.list_models', {
      kind,
      base_url: creds.base_url,
      api_key: creds.api_key,
    });
    if (answer === null || !alive) return;
    models = answer.models || [];
  }

  /** Поправить поле.
   *
   * Перечень имён спрашивается заново на смене адреса или ключа: он с них и
   * читается, и оставленный прежним подсказывал бы модели чужого сервера.
   */
  function edit(part) {
    creds = { ...creds, ...part };
    // Плашка проверки говорит про те данные, которые проверяли: правь их — ей
    // верить больше нельзя.
    probe = idleProbe();
    if (part.model === undefined) return listModels();
  }

  /** Выбрать готового поставщика: адрес подставляется, ключ и модель остаются
   *  набранными — у одного поставщика их и меняют, перебирая адреса. */
  function pickPreset(label) {
    const preset = PRESETS.find((one) => one.label === label);
    if (preset === undefined) return;
    return edit({ base_url: preset.base_url });
  }

  /** Проверить связь с поставщиком.
   *
   * Мосту едут набранные данные, а не сохранённые: в мастере сохранённых ещё
   * нет вовсе, и проверять было бы нечего.
   */
  async function check() {
    probe = { ...idleProbe(), status: 'busy' };
    let answer = null;
    let refused = '';
    try {
      // Зовём мост напрямую: отказ поставщика — это и есть исход проверки, и
      // человек читает его в плашке рядом с полем.
      answer = await call('settings.probe_model', { kind, ...creds });
    } catch (refusal) {
      refused = refusal.message;
    }
    if (!alive || probe.status !== 'busy') return;
    if (answer === null) {
      probe = { ...idleProbe(), status: 'err', error: refused };
      return;
    }
    probe = {
      status: 'ok',
      model: answer.model || '',
      latencyMs: answer.latency_ms || 0,
      error: '',
    };
  }

  async function save() {
    // Заслон уже назван рядом с кнопкой; нажатие при нём ничего не делает.
    if (trouble || saving) return;
    saving = true;
    // Адрес уезжает обрезанным: заслон судит по обрезанному, и пробел на конце
    // прошёл бы проверку, а на мост уехал бы вместе с ним.
    creds = { ...creds, base_url: creds.base_url.trim() };
    const done = await ask('settings.save', kind === 'chat' ? { chat: creds } : { embed: creds });
    if (!alive) return;
    saving = false;
    if (done === null) return;
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
  <div class="wiz-title">{title}</div>
  <p class="wiz-text">
    {kind === 'chat'
      ? 'Этой моделью бот разбирает объявления и сочиняет письма. Подойдёт и местная, запущенная на этом компьютере, и облачная.'
      : 'Этой моделью бот сравнивает вакансии с вашей анкетой. Она может быть той же, что и для чата, — тогда оставьте адрес и ключ прежними.'}
  </p>

  <ChoiceRow
    options={PRESETS.map((one) => ({ value: one.label, label: one.label }))}
    chosen={new Set([chosenPreset])}
    look="chip"
    onpick={pickPreset}
  />

  <LlmSection
    {icon}
    {title}
    {creds}
    {models}
    {pill}
    busy={probe.status === 'busy'}
    onsave={edit}
    onprobe={check}
  />
</div>

<WizardFoot {trouble} nextLabel="Дальше" busy={saving} {onback} onnext={save} />
