<script>
  // Вкладка «CV»: анкета и файл резюме.
  //
  // Записывается по ходу, как и настройки: поле уезжает на мост, когда его
  // покидают. Мост принимает анкету целиком, поэтому уезжает она вся — но
  // собранная из свежего состояния, а не из снимка.

  import { call } from '$api/bridge.js';
  import CvFileRow from '$components/CvFileRow.svelte';
  import LangRows from '$components/LangRows.svelte';
  import ChoiceRow from '$components/ChoiceRow.svelte';
  import { toggled } from '$state/chosen.js';
  import { GRADES, WORK_FORMATS, blankProfile, langRow, updatedNote } from '$state/profile.js';

  let { ask } = $props();

  // Длины те же, что у полей базы: обрезать текст мост не станет, он ответит
  // отказом — а человек к тому мигу уже набрал лишнее и потерял бы набранное.
  const FIELDS = [
    { key: 'first_name', placeholder: 'Имя *', max: 64 },
    { key: 'last_name', placeholder: 'Фамилия *', max: 64 },
    { key: 'title', placeholder: 'Должность *', max: 120, wide: true },
    { key: 'email', placeholder: 'Email *', max: 254 },
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

  let alive = true;

  async function refresh() {
    const now = await ask('profile.get');
    if (now === null || !alive) return;
    form = now.profile || blankProfile();
    meta = now.cv_meta;
    grades = new Set(form.grades);
    formats = new Set(form.work_format);
    loaded = true;
  }

  /** Отправить анкету целиком.
   *
   * Мост принимает её только так и отказывает, пока не заполнены четверо
   * обязательных. Отказ этот — обычное дело: анкету заполняют сверху вниз, и
   * до последнего обязательного поля каждая запись законно отказана. Поэтому
   * он живёт строкой под формой, а не общей плашкой окна: плашка била бы на
   * каждом поле и закрывала бы собой соседние.
   */
  async function save() {
    try {
      await call('profile.save', {
        ...form,
        grades: [...grades],
        work_format: [...formats],
      });
      if (!alive) return;
      trouble = '';
      await refresh();
    } catch (refusal) {
      if (alive) trouble = refusal.message;
    }
  }

  function edit(key, value) {
    form = { ...form, [key]: value };
    return save();
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

  /** Выбрать другой файл резюме.
   *
   * Путь спрашивает мост диалогом самого окна: браузер отдаёт выбранный файл
   * содержимым, а не путём, — а отклику нужен именно путь.
   */
  async function replaceCv() {
    const answer = await ask('profile.pick');
    if (answer === null || !alive || answer.cancelled) return;
    await refresh();
  }

  async function openCv() {
    await ask('profile.open');
  }

  $effect(() => {
    alive = true;
    refresh();
    return () => {
      alive = false;
    };
  });
</script>

{#if !loaded}
  <div class="empty-note">Загрузка…</div>
{:else}
  <div class="page-head">
    <div class="page-title">Профиль / CV</div>
    <div class="updated-ts">{updatedNote(form.updated_at)}</div>
  </div>

  <div class="form-grid">
    {#each FIELDS as one (one.key)}
      <input
        class="input"
        class:span-2={one.wide}
        maxlength={one.max}
        placeholder={one.placeholder}
        value={form[one.key]}
        onblur={(event) => edit(one.key, event.currentTarget.value.trim())}
      />
    {/each}

    <textarea
      class="textarea span-2"
      maxlength="1000"
      placeholder="Образование"
      value={form.education}
      onblur={(event) => edit('education', event.currentTarget.value.trim())}
    ></textarea>

    <ChoiceRow options={GRADES} chosen={grades} look="seg" onpick={pickGrade} />
    <ChoiceRow options={WORK_FORMATS} chosen={formats} look="seg" onpick={pickFormat} />

    <LangRows rows={form.languages} onedit={editLang} onadd={addLang} onremove={dropLang} />

    <textarea
      class="textarea span-2"
      maxlength="2000"
      placeholder="Личные предпочтения — что важно при выборе работы, что точно не подойдёт"
      value={form.free_preferences}
      onblur={(event) => edit('free_preferences', event.currentTarget.value.trim())}
    ></textarea>
  </div>

  <CvFileRow {meta} onreplace={replaceCv} onopen={openCv} />

  {#if trouble}
    <div class="save-trouble">{trouble}</div>
  {/if}
{/if}
