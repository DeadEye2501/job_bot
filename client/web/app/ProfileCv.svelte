<script>
  // Вкладка «CV»: анкета и файл резюме.
  //
  // Записывается по ходу, как и настройки: набранное уезжает, когда человек
  // остановился, ушёл из поля или попросил записать с клавиатуры. Мост
  // принимает анкету целиком, поэтому уезжает она вся — но собранная из
  // свежего состояния, а не из снимка.

  import { call } from '$api/bridge.js';
  import CvFileRow from '$components/CvFileRow.svelte';
  import DelayedTextarea from '$components/DelayedTextarea.svelte';
  import Dropdown from '$components/Dropdown.svelte';
  import LangRows from '$components/LangRows.svelte';
  import ChoiceRow from '$components/ChoiceRow.svelte';
  import { living } from '$state/alive.js';
  import { autosave } from '$state/autosave.js';
  import { saveKey } from '$state/keys.js';
  import { oneWrite } from '$state/one_write.js';
  import { alone, toggled } from '$state/chosen.js';
  import {
    CURRENCIES,
    GENDERS,
    GRADES,
    SALARY_PERIODS,
    WORK_FORMATS,
    blankProfile,
    cvOpenable,
    langRow,
    profileSheet,
    updatedNote,
  } from '$state/profile.js';

  // Пауза перед записью набранного. Короче — и мост получает вопрос на каждое
  // слово, длиннее — и человек успевает уйти с вкладки, не дождавшись записи.
  const TYPING_DELAY = 800;

  let { ask } = $props();

  // Пределы длины держит только окно: ни мост, ни база длину полей анкеты не
  // меряют. `must` — поле, без которого мост анкету не примет вовсе. Звёздочка в
  // подсказке говорит о том же, но только пока поле пустое и подсказка видна.
  const NAME_FIELDS = [
    { key: 'first_name', placeholder: 'Имя *', max: 64, must: true },
    { key: 'last_name', placeholder: 'Фамилия *', max: 64, must: true },
  ];
  const LATIN_FIELDS = [
    { key: 'first_name_latin', placeholder: 'Имя латиницей', max: 64 },
    { key: 'last_name_latin', placeholder: 'Фамилия латиницей', max: 64 },
  ];
  const FIELDS = [
    { key: 'title', placeholder: 'Должность *', max: 120, wide: true, must: true },
    { key: 'email', placeholder: 'Email *', max: 254, must: true },
    { key: 'phone', placeholder: 'Телефон', max: 32 },
    { key: 'telegram_username', placeholder: 'Telegram (@username)', max: 64 },
    { key: 'github_url', placeholder: 'GitHub (URL)', max: 255 },
    { key: 'location', placeholder: 'Локация', max: 120, wide: true },
  ];

  let loaded = $state(false);
  let trouble = $state('');
  let form = $state(null);
  let meta = $state(null);
  let grades = $state(new Set());
  let formats = $state(new Set());
  let fields = $state(null);

  const alive = living();

  // Отложенная запись одна на всю анкету: мост принимает её целиком, и держать
  // по отсчёту на поле значило бы слать одно и то же по разу на поле.
  const saver = autosave({ delay: TYPING_DELAY, save: () => save() });

  async function refresh() {
    const now = await ask('profile.get');
    if (now === null || !alive.now) return;
    meta = now.cv_meta;
    const fresh = now.profile || blankProfile();
    // Пока курсор стоит в форме, с моста берётся одна отметка о правке:
    // остальное человек сейчас и набирает, а анкету перечитывают в том числе
    // на свою же запись — пришедшее посреди набора стёрло бы набранное.
    if (loaded && fields && fields.contains(document.activeElement)) {
      form = { ...form, updated_at: fresh.updated_at };
      return;
    }
    form = fresh;
    grades = new Set(form.grades);
    formats = new Set(form.work_format);
    loaded = true;
  }

  function sheet() {
    return profileSheet(form, grades, formats);
  }

  /** Отдать анкету мосту и сказать, легла ли она.
   *
   * Мост принимает её только целиком и отказывает, пока не заполнены четверо
   * обязательных. Отказ этот — обычное дело: анкету заполняют сверху вниз, и до
   * последнего обязательного поля каждая запись законно отказана. Поэтому он
   * живёт строкой под формой и отметкой на самих незаполненных полях, а не
   * общей плашкой окна: плашка била бы на каждом поле и закрывала бы соседние.
   */
  async function send(sending) {
    try {
      await call('profile.save', sending);
      if (!alive.now) return false;
      trouble = '';
      await refresh();
      return true;
    } catch (refusal) {
      if (alive.now) trouble = refusal.message;
      return false;
    }
  }

  const write = oneWrite(send);

  /** Отправить анкету целиком. */
  function save() {
    const sending = sheet();
    // Уехавшее — оно же и «лежит в базе»: без этого уход из нетронутого поля
    // отправил бы ту же анкету заново. Ставится и здесь, потому что анкету шлёт
    // не только отсчёт: выбор грейда, формата и языка зовёт запись напрямую.
    saver.known(JSON.stringify(sending));
    return write(sending);
  }

  /** Набранное в поле: в анкету ложится сразу, на мост уедет по остановке.
   *
   * Отсчёт ведётся по всей анкете, а не по полю: то, чем поля отличаются друг
   * от друга, мосту всё равно не видно — он получает их разом.
   *
   * Обрезка здесь, а не при отправке: в поле остаётся набранное как есть, а
   * лишний пробел на его краю не считается правкой и записи не будит.
   */
  function typed(key, value) {
    form = { ...form, [key]: value.trim() };
    saver.typed(JSON.stringify(sheet()));
  }

  function editLang(index, part) {
    const rows = form.languages.map((one, at) => (at === index ? { ...one, ...part } : one));
    form = { ...form, languages: rows };
    return save();
  }

  function addLang() {
    form = { ...form, languages: [...form.languages, langRow()] };
  }

  function dropLang(index) {
    form = { ...form, languages: form.languages.filter((_, at) => at !== index) };
    return save();
  }

  function pickGrade(value) {
    grades = toggled(grades, value);
    return save();
  }

  function pickFormat(value) {
    formats = toggled(formats, value);
    return save();
  }

  /** Валюту из списка выбирают, а не переключают: выбранная повторно остаётся. */
  function pickCurrency(sign) {
    form = { ...form, expected_salary_currency: sign };
    return save();
  }

  /** Пол и срок зарплаты — по одному значению; нажатое повторно снимается. */
  function pickOne(key, value) {
    form = { ...form, [key]: alone(form[key], value) };
    return save();
  }

  /** Выбрать другой файл резюме.
   *
   * Путь спрашивает мост диалогом самого окна: браузер отдаёт выбранный файл
   * содержимым, а не путём, — а отклику нужен именно путь.
   */
  async function replaceCv() {
    const answer = await ask('profile.pick');
    if (answer === null || !alive.now || answer.cancelled) return;
    await refresh();
  }

  async function openCv() {
    await ask('profile.open');
  }

  $effect(() => {
    return alive.entered(refresh);
  });
</script>

{#if !loaded}
  <div class="placeholder-content">Загрузка…</div>
{:else}
  <div class="page-head">
    <div class="page-title">Профиль / CV</div>
    <div class="updated-ts">{updatedNote(form.updated_at)}</div>
  </div>

  {#snippet field(one)}
    <input
      class="input"
      class:span-2={one.wide}
      class:missing={trouble && one.must && !form[one.key].trim()}
      maxlength={one.max}
      inputmode={one.mode}
      placeholder={one.placeholder}
      value={form[one.key] ?? ''}
      oninput={(event) => typed(one.key, event.currentTarget.value)}
      onblur={() => saver.flush()}
      onkeydown={(event) => saveKey(event) && saver.flush()}
    />
  {/snippet}

  <div class="form-grid" bind:this={fields}>
    <div class="name-grid span-2">
      <div class="input-pair">
        {#each NAME_FIELDS as one (one.key)}{@render field(one)}{/each}
      </div>
      <div class="input-pair">
        {#each LATIN_FIELDS as one (one.key)}{@render field(one)}{/each}
      </div>
      <ChoiceRow
        options={GENDERS}
        chosen={new Set([form.gender])}
        look="tile"
        onpick={(value) => pickOne('gender', value)}
      />
    </div>

    {#each FIELDS as one (one.key)}{@render field(one)}{/each}

    <div class="field-line span-2">
      {@render field({
        key: 'expected_salary',
        placeholder: 'Ожидаемая зарплата на руки',
        max: 12,
        mode: 'numeric',
      })}
      <div class="field-narrow">
        <Dropdown
          options={CURRENCIES}
          value={form.expected_salary_currency}
          placeholder="—"
          onpick={pickCurrency}
        />
      </div>
      <ChoiceRow
        options={SALARY_PERIODS}
        chosen={new Set([form.expected_salary_period])}
        look="seg"
        onpick={(value) => pickOne('expected_salary_period', value)}
      />
    </div>

    <DelayedTextarea
      maxlength="1000"
      placeholder="Образование"
      value={form.education}
      ontyped={(text) => typed('education', text)}
      onflush={() => saver.flush()}
    />

    <ChoiceRow options={GRADES} chosen={grades} look="seg" onpick={pickGrade} />
    <ChoiceRow options={WORK_FORMATS} chosen={formats} look="seg" onpick={pickFormat} />

    <LangRows rows={form.languages} onedit={editLang} onadd={addLang} onremove={dropLang} />

    <DelayedTextarea
      maxlength="2000"
      placeholder="Личные предпочтения — что важно при выборе работы, что точно не подойдёт"
      value={form.free_preferences}
      ontyped={(text) => typed('free_preferences', text)}
      onflush={() => saver.flush()}
    />
  </div>

  <CvFileRow {meta}>
    {#snippet actions()}
      <button class="btn" type="button" onclick={replaceCv}>Заменить</button>
      <button class="btn" type="button" disabled={!cvOpenable(meta)} onclick={openCv}>
        Открыть
      </button>
    {/snippet}
  </CvFileRow>

  {#if trouble}
    <div class="autosave-error">{trouble}</div>
  {/if}
{/if}
