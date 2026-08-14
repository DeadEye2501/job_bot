<script>
  // Место работы: свёрнутая шапка и всё остальное под ней.
  import { asIso, cardTitle, showDate } from '$state/experience.js';

  import BulletList from './BulletList.svelte';
  import SkillPicker from './SkillPicker.svelte';

  let { exp, known, open, ontoggle, onedit, onremove } = $props();

  const title = $derived(cardTitle(exp));

  // «Работаю сейчас» — это признак самой карточки, а не пустая дата окончания.
  // Выводи мы его из даты, снятая галочка тут же возвращалась бы: даты-то ещё
  // нет, человек только собирается её набрать.
  let current = $state(!exp.end_date);

  function switchCurrent(on) {
    current = on;
    // Дату окончания стираем только при включении. При снятии не сочиняем
    // ничего: поле отпирается пустым, и человек вписывает свою.
    if (on) onedit({ end_date: null });
  }

  /** Принять набранную дату.
   *
   * Недобранное не отправляем и поле не трогаем: человек продолжает набирать.
   */
  function pickDate(key, text) {
    const iso = asIso(text);
    if (iso !== null || text.trim() === '') onedit({ [key]: iso });
  }

  function editItem(field, index, text) {
    onedit({ [field]: exp[field].map((one, at) => (at === index ? text : one)) });
  }
</script>

<div class="collapsible" class:collapsed={!open}>
  <div class="collapsible-head">
    <button class="icon-btn" type="button" onclick={() => ontoggle()}>
      <span class="material-symbols-outlined">expand_more</span>
    </button>
    <div class="exp-summary">
      <strong>{title.company}</strong>
      {#if title.role}<span class="role">· {title.role}</span>{/if}
      {#if title.period}<span class="period">{title.period}</span>{/if}
    </div>
    <button
      class="icon-btn"
      type="button"
      title="Удалить место работы"
      onclick={() => onremove()}
    >
      <span class="material-symbols-outlined">delete</span>
    </button>
  </div>

  {#if open}
    <div class="exp-body">
      <div class="form-grid">
        <input
          class="input"
          maxlength="255"
          placeholder="Компания"
          value={exp.company}
          onblur={(event) => onedit({ company: event.currentTarget.value.trim() })}
        />
        <input
          class="input"
          maxlength="255"
          placeholder="URL компании"
          value={exp.company_url || ''}
          onblur={(event) => onedit({ company_url: event.currentTarget.value.trim() })}
        />
        <input
          class="input span-2"
          maxlength="120"
          placeholder="Должность"
          value={exp.role || ''}
          onblur={(event) => onedit({ role: event.currentTarget.value.trim() })}
        />

        <div class="date-pair span-2">
          <input
            class="input-date"
            maxlength="10"
            placeholder="дд.мм.гггг"
            value={showDate(exp.start_date)}
            onblur={(event) => pickDate('start_date', event.currentTarget.value)}
          />
          <span class="date-dash">—</span>
          <input
            class="input-date"
            maxlength="10"
            placeholder="дд.мм.гггг"
            value={showDate(exp.end_date)}
            disabled={current}
            onblur={(event) => pickDate('end_date', event.currentTarget.value)}
          />
          <label class="checkbox-row">
            <input
              type="checkbox"
              checked={current}
              onchange={(event) => switchCurrent(event.currentTarget.checked)}
            />
            по настоящее время
          </label>
        </div>
      </div>

      <BulletList
        label="Достижения"
        addLabel="Добавить достижение"
        items={exp.achievements}
        onedit={(index, text) => editItem('achievements', index, text)}
        onadd={() => onedit({ achievements: [...exp.achievements, ''] })}
        onremove={(index) =>
          onedit({ achievements: exp.achievements.filter((_, at) => at !== index) })}
      />

      <BulletList
        label="Обязанности"
        addLabel="Добавить обязанность"
        items={exp.responsibilities}
        onedit={(index, text) => editItem('responsibilities', index, text)}
        onadd={() => onedit({ responsibilities: [...exp.responsibilities, ''] })}
        onremove={(index) =>
          onedit({ responsibilities: exp.responsibilities.filter((_, at) => at !== index) })}
      />

      <div class="list-block">
        <div class="field-label"><span>Стек</span></div>
        <SkillPicker
          chosen={exp.skill_names}
          {known}
          onadd={(name) => onedit({ skill_names: [...exp.skill_names, name] })}
          onremove={(index) =>
            onedit({ skill_names: exp.skill_names.filter((_, at) => at !== index) })}
        />
      </div>
    </div>
  {/if}
</div>
