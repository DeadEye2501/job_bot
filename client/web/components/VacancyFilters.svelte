<script>
  // Отбор вакансий: кнопка-воронка и панель девяти условий под ней.
  //
  // Правки идут в черновик, а список перечитывается по «Применить»: условий
  // девять, и на лету панель стоила бы десятка зовов моста подряд, каждый из
  // которых перебирает всю базу.
  import { toggled } from '$state/chosen.js';
  import {
    DATE_PRESETS,
    GRADE_CHOICES,
    HR_CHOICES,
    REMOTE_CHOICES,
    STATUS_CHOICES,
    activeCount,
    blankFilter,
    pickNames,
  } from '$state/vacancy_filter.js';

  import ChoiceRow from './ChoiceRow.svelte';
  import FilterGroup from './FilterGroup.svelte';
  import PickList from './PickList.svelte';

  let { applied, options, onapply } = $props();

  let shown = $state(false);
  // Наборы черновика делятся с применённым отбором, пока их не тронули: правят
  // их только через `toggled`, а он возвращает новый набор. Правка на месте
  // (`draft.statuses.add`) поехала бы и в применённый — «Отмена» перестала бы
  // отменять.
  let draft = $state(blankFilter());
  let channelSearch = $state('');
  let companySearch = $state('');

  const count = $derived(activeCount(draft, new Date()));
  const channels = $derived(pickNames(options.channels, channelSearch));
  const companies = $derived(pickNames(options.companies, companySearch));

  // Одиночный выбор ряду вариантов приходит набором из одного: сам ряд про то,
  // один выбран или несколько, не знает.
  const alone = (value) => new Set([value]);

  function toggle() {
    if (!shown) {
      draft = { ...applied };
      channelSearch = '';
      companySearch = '';
    }
    shown = !shown;
  }

  $effect(() => {
    if (!shown) return;
    // Нажатие мимо панели закрывает её и бросает черновик. Ухода мыши здесь
    // мало: панель большая, и мышь уходит с неё, пока человек ещё набирает.
    const away = (event) => {
      if (!event.target.closest('.filter-wrap')) shown = false;
    };
    document.addEventListener('click', away);
    return () => document.removeEventListener('click', away);
  });
</script>

<div class="filter-wrap">
  <button
    class="icon-btn filter-btn"
    class:active={activeCount(applied, new Date()) > 0}
    type="button"
    title="Фильтры"
    onclick={toggle}
  >
    <span class="material-symbols-outlined">filter_list</span>
  </button>

  {#if shown}
    <div class="filter-panel">
      <div class="filter-head">
        <span class="material-symbols-outlined">filter_list</span>
        <span class="filter-title">Фильтры</span>
        <span class="filter-meta">{count ? `${count} активных` : 'Без фильтров'}</span>
        <button class="icon-btn" type="button" title="Закрыть" onclick={() => (shown = false)}>
          <span class="material-symbols-outlined">close</span>
        </button>
      </div>

      <div class="filter-body">
        <FilterGroup label="Статус">
          <ChoiceRow
            options={STATUS_CHOICES}
            chosen={draft.statuses}
            look="chip"
            dots
            onpick={(value) => (draft.statuses = toggled(draft.statuses, value))}
          />
        </FilterGroup>

        <FilterGroup label="Каналы">
          <PickList
            placeholder="Выбрать каналы"
            names={channels}
            chosen={draft.channels}
            search={channelSearch}
            onsearch={(text) => (channelSearch = text)}
            prefix="@"
            onpick={(name) => (draft.channels = toggled(draft.channels, name))}
          />
        </FilterGroup>

        <FilterGroup label="Компании">
          <PickList
            placeholder="Выбрать компании"
            names={companies}
            chosen={draft.companies}
            search={companySearch}
            onsearch={(text) => (companySearch = text)}
            onpick={(name) => (draft.companies = toggled(draft.companies, name))}
          />
        </FilterGroup>

        <FilterGroup label="Оценка">
          <div class="filter-pair">
            <!-- Шаг целый: оценку мост читает целым числом, и набранное «60.5»
                 он молча срезал бы до шестидесяти. -->
            <input
              class="input"
              type="number"
              step="1"
              placeholder="от"
              value={draft.scoreMin}
              oninput={(event) => (draft.scoreMin = event.currentTarget.value)}
            />
            <input
              class="input"
              type="number"
              step="1"
              placeholder="до"
              value={draft.scoreMax}
              oninput={(event) => (draft.scoreMax = event.currentTarget.value)}
            />
          </div>
        </FilterGroup>

        <FilterGroup label="Зарплата">
          <div class="filter-pair">
            <input
              class="input"
              type="number"
              placeholder="от"
              value={draft.salaryMin}
              oninput={(event) => (draft.salaryMin = event.currentTarget.value)}
            />
            <input
              class="input"
              type="number"
              placeholder="до"
              value={draft.salaryMax}
              oninput={(event) => (draft.salaryMax = event.currentTarget.value)}
            />
          </div>
        </FilterGroup>

        <FilterGroup label="Грейд">
          <ChoiceRow
            options={GRADE_CHOICES}
            chosen={alone(draft.grade)}
            look="chip"
            onpick={(value) => (draft.grade = value)}
          />
        </FilterGroup>

        <FilterGroup label="Формат работы">
          <ChoiceRow
            options={REMOTE_CHOICES}
            chosen={alone(draft.remote)}
            look="chip"
            onpick={(value) => (draft.remote = value)}
          />
        </FilterGroup>

        <FilterGroup label="Контакт HR">
          <ChoiceRow
            options={HR_CHOICES}
            chosen={alone(draft.hrContact)}
            look="chip"
            onpick={(value) => (draft.hrContact = value)}
          />
        </FilterGroup>

        <FilterGroup label="Активность в течение">
          <ChoiceRow
            options={DATE_PRESETS}
            chosen={alone(draft.datePreset)}
            look="chip"
            onpick={(value) => (draft.datePreset = value)}
          />
          {#if draft.datePreset === 'range'}
            <div class="filter-pair filter-dates">
              <input
                class="input"
                type="text"
                placeholder="дд.мм.гггг"
                maxlength="10"
                value={draft.dateFrom}
                oninput={(event) => (draft.dateFrom = event.currentTarget.value)}
              />
              <input
                class="input"
                type="text"
                placeholder="дд.мм.гггг"
                maxlength="10"
                value={draft.dateTo}
                oninput={(event) => (draft.dateTo = event.currentTarget.value)}
              />
            </div>
          {/if}
        </FilterGroup>
      </div>

      <div class="filter-foot">
        <!-- «Сбросить» — это «показать всё», а не «очистить поля»: список
             перечитывается сразу, панель закрывается. -->
        <button
          class="btn"
          type="button"
          onclick={() => {
            shown = false;
            onapply(blankFilter());
          }}
        >
          Сбросить
        </button>
        <div class="filter-foot-right">
          <button class="btn" type="button" onclick={() => (shown = false)}>Отмена</button>
          <button
            class="btn primary"
            type="button"
            onclick={() => {
              shown = false;
              onapply({ ...draft });
            }}
          >
            Применить
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>
