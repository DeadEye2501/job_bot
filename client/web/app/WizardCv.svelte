<script>
  // Шаг мастера: резюме.
  //
  // Единственный шаг, который можно пропустить: без резюме бот работает — он
  // не сможет только приложить его к отклику, а дописать файл человек успеет
  // потом, в анкете. Пропуск при этом называется вслух, отдельным выбором:
  // молчаливо пройденный шаг человек считал бы приложенным резюме.
  import { call } from '$api/bridge.js';
  import { living } from '$state/alive.js';
  import CvFileRow from '$components/CvFileRow.svelte';
  import WizardFoot from '$components/WizardFoot.svelte';
  import WizardStatus from '$components/WizardStatus.svelte';
  import { cvModes, cvReady } from '$state/wizard.js';

  let { ask, busy, events, onback, onnext } = $props();

  const MODES = cvModes();

  let cv = $state(null);
  let path = $state('');
  let mode = $state('attach');
  let loaded = $state(false);
  let saving = $state(false);
  let parsing = $state(false);
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
    if (mode === 'parse') return parse();
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

  /** Пустить разбор и остаться ждать его вести.
   *
   * Шаг ждёт, а не уходит вперёд: разбор заменяет анкету целиком, и уйди
   * человек с шага раньше исхода — мастер закончился бы, подняв бота посреди
   * работы, а анкета доехала бы уже после.
   */
  async function parse() {
    parsing = true;
    status = { tone: 'busy', text: 'Разбираем резюме — это займёт около минуты.' };
    const started = await ask('profile.parse_cv');
    // Исход успевает прийти раньше ответа на сам зов: пропавший файл и
    // нечитаемый формат отвечают вестью сразу. Сказанное им — последнее слово
    // о шаге, и дописывать после него нечего.
    if (!alive.now || started !== null) return;
    parsing = false;
    saving = false;
    status = null;
  }

  /** Разбор кончился: удавшийся уводит дальше, сорвавшийся отдаёт шаг обратно.
   *
   * Слушаем только пока сами разбираем: весть эта общая на все долгие работы,
   * и чужая увела бы человека с шага, которого он не заканчивал.
   */
  async function parsed(done) {
    if (!parsing) return;
    parsing = false;
    if (done.danger) {
      saving = false;
      status = { tone: 'err', text: done.message };
      return;
    }
    await onnext();
    if (!alive.now) return;
    saving = false;
    status = null;
  }

  $effect(() => {
    return alive.entered(refresh);
  });

  $effect(() => {
    return events.on('action_finished', parsed);
  });
</script>

<div class="wiz-body">
  <div class="wiz-title">Резюме</div>
  <div class="wiz-subtitle">
    Файл резюме в <strong>PDF</strong>, <strong>DOCX</strong>, <strong>Markdown</strong>
    или <strong>txt</strong>.
    Используется для автозаполнения профиля и хранится локально.
  </div>

  {#if loaded}
    <CvFileRow meta={cv}>
      {#snippet actions()}
        <button class="btn" type="button" disabled={saving} onclick={pick}>
          {cv ? 'Заменить' : 'Выбрать'}
        </button>
      {/snippet}
    </CvFileRow>
  {/if}

  <div class="wiz-modes">
    {#each MODES as one (one.id)}
      <label
        class="radio-card"
        class:selected={mode === one.id}
        class:disabled={one.disabled || saving}
      >
        <input
          type="radio"
          name="cvmode"
          value={one.id}
          disabled={one.disabled || saving}
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
