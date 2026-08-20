<script>
  // Шаг мастера: резюме.
  //
  // Единственный шаг, который можно пропустить: без резюме бот работает — он
  // не сможет только приложить его к отклику, а дописать файл человек успеет
  // потом, в анкете. Пропуск при этом называется вслух, отдельным выбором:
  // молчаливо пройденный шаг человек считал бы приложенным резюме.
  import { call } from '$api/bridge.js';
  import { living } from '$state/alive.js';
  import { fileSize } from '$state/profile.js';
  import WizardFoot from '$components/WizardFoot.svelte';
  import WizardStatus from '$components/WizardStatus.svelte';
  import { cvModes, cvReady } from '$state/wizard.js';

  let { ask, busy, onback, onnext } = $props();

  const MODES = cvModes();

  let cv = $state(null);
  let path = $state('');
  let mode = $state('attach');
  let loaded = $state(false);
  let saving = $state(false);
  let status = $state(null);

  const alive = living();

  async function refresh() {
    const now = await ask('profile.get');
    if (now === null || !alive.now) return;
    cv = now.cv_meta;
    path = now.cv_path;
    loaded = true;
  }

  /** Выбрать файл. Строка состояния гаснет: сказанное ею относилось к тому,
   *  что было выбрано до диалога. */
  async function pick() {
    const now = await ask('profile.pick');
    if (now === null || !alive.now) return;
    status = null;
    return refresh();
  }

  /** Закончить шаг.
   *
   * Заслон назван строкой состояния, а не запертой кнопкой: запертая оставляет
   * человека гадать, чего ей не хватило, — а не хватить может и файла, и
   * выбранного вслух отказа от него.
   */
  async function finish() {
    if (!cvReady({ mode, path })) {
      status = { tone: 'err', text: 'Выберите файл или вариант «Пропустить шаг».' };
      return;
    }
    saving = true;
    status = { tone: 'busy', text: 'Сохраняем...' };
    if (mode === 'skip' && !(await forget())) return;
    if (!alive.now) return;
    await onnext();
    // Досюда доходят, только если закончить не удалось: удавшееся уводит на
    // финал вместе с этим экраном. Кнопки отпираются обратно — иначе человек
    // остался бы на шаге, с которого больше некуда нажать.
    if (!alive.now) return;
    saving = false;
    status = null;
  }

  /** Забыть записанный путь к резюме; отвечает, вышло ли.
   *
   * Мост зовётся напрямую, а не через `ask`: отказ здесь — это и есть исход
   * шага, и человек читает его строкой под карточками, а не плашкой поверх
   * окна, куда он в этот миг не смотрит.
   */
  async function forget() {
    try {
      await call('wizard.skip_cv');
    } catch (refusal) {
      if (!alive.now) return false;
      saving = false;
      status = { tone: 'err', text: refusal.message };
      return false;
    }
    return true;
  }

  $effect(() => {
    const settled = alive.mounted();
    refresh();
    return () => {
      settled();
    };
  });
</script>

<div class="wiz-body">
  <div class="wiz-title">Резюме</div>
  <div class="wiz-subtitle">
    Файл резюме в <strong>PDF</strong>, <strong>Markdown</strong> или <strong>txt</strong>.
    Используется для автозаполнения профиля и хранится локально.
  </div>

  {#if loaded}
    <div class="file-pick" class:has-file={!!cv}>
      <span class="material-symbols-outlined">{cv ? 'description' : 'upload_file'}</span>
      <span class="text">
        {#if cv}
          <span class="name">{cv.name}</span> · {fileSize(cv.size)}
        {:else}
          Файл ещё не выбран
        {/if}
      </span>
      <button class="btn" type="button" onclick={pick}>{cv ? 'Заменить' : 'Выбрать'}</button>
    </div>
  {/if}

  <div class="wiz-modes">
    {#each MODES as one (one.id)}
      <label class="radio-card" class:selected={mode === one.id} class:disabled={one.disabled}>
        <input
          type="radio"
          name="cvmode"
          value={one.id}
          disabled={one.disabled}
          bind:group={mode}
        />
        <div>
          <div class="rc-title">{one.title}</div>
          <div class="rc-sub">{one.note}</div>
        </div>
      </label>
    {/each}
  </div>

  <WizardStatus {status} />
</div>

<WizardFoot
  nextLabel="Готово"
  nextIcon="check"
  busy={busy || saving || !loaded}
  {onback}
  onnext={finish}
/>
