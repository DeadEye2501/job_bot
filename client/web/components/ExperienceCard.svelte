<script>
  // Место работы: свёрнутая шапка и всё остальное под ней.
  import { cardTitle } from '$state/experience.js';

  import BulletList from './BulletList.svelte';
  import DatePicker from './DatePicker.svelte';
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
    // ничего: стёртую дату поле уже показало пустой — оно идёт за доводом, — и
    // человек вписывает в него свою.
    if (on) onedit({ end_date: null });
  }

  /** Принять выбранную дату.
   *
   * Стёртое поле уходит пустотой, а не пустой строкой: `null` мост понимает как
   * «даты нет», и им же стирает дату окончания галочка «по настоящее время».
   */
  function pickDate(key, iso) {
    onedit({ [key]: iso || null });
  }

  function editItem(field, index, text) {
    onedit({ [field]: exp[field].map((one, at) => (at === index ? text : one)) });
  }
</script>

<div class="exp-card" class:collapsed={!open}>
  <!-- Нажимается вся шапка, а не одна стрелка: свёрнутых карточек столбик, и
       целиться в значок ради раскрытия человеку не за что. -->
  <div
    class="exp-header"
    role="button"
    tabindex="0"
    onclick={() => ontoggle()}
    onkeydown={(event) => event.key === 'Enter' && ontoggle()}
  >
    <span class="material-symbols-outlined collapse-arrow">expand_more</span>
    <div class="exp-summary">
      <strong>{title.company}</strong>
      {#if title.role}· <span class="role">{title.role}</span>{/if}
      {#if title.period}<span class="period">{title.period}</span>{/if}
    </div>
    <button
      class="exp-delete"
      type="button"
      title="Удалить место работы"
      onclick={(event) => {
        event.stopPropagation();
        onremove();
      }}
    >
      <span class="material-symbols-outlined">delete</span>
    </button>
  </div>

  {#if open}
    <div class="exp-body">
      <div class="field-row">
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
          <DatePicker value={exp.start_date} onpick={(iso) => pickDate('start_date', iso)} />
          <span class="date-dash">—</span>
          <DatePicker
            value={exp.end_date}
            disabled={current}
            onpick={(iso) => pickDate('end_date', iso)}
          />
          <label class="date-current">
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
