<script>
  // Отбор вакансий: кнопка-воронка и панель девяти условий под ней.
  //
  // Правки идут в черновик, а список перечитывается по «Применить»: условий
  // девять, и на лету панель стоила бы десятка зовов моста подряд, каждый из
  // которых перебирает всю базу.
  import { tick } from 'svelte';

  import { toggled } from '$state/chosen.js';
  import { whileOpen } from '$state/outside.js';
  import { STATUS_CHOICES } from '$state/statuses.js';
  import {
    COMPANY_MAX,
    DATE_PRESETS,
    GRADE_CHOICES,
    HR_CHOICES,
    REMOTE_CHOICES,
    activeCount,
    blankFilter,
    pickNames,
  } from '$state/vacancy_filter.js';

  import ChoiceRow from './ChoiceRow.svelte';
  import DatePicker from './DatePicker.svelte';
  import FilterGroup from './FilterGroup.svelte';
  import PickList from './PickList.svelte';

  // Открыта ли панель — знает экран, а не она сама: меню порядка стоит рядом,
  // и открытое разом с панелью оно накрывало бы её собой.
  let { applied, options, onapply, shown, onshown } = $props();
  // Наборы черновика делятся с применённым отбором, пока их не тронули: правят
  // их только через `toggled`, а он возвращает новый набор. Правка на месте
  // (`draft.statuses.add`) поехала бы и в применённый — «Отмена» перестала бы
  // отменять.
  let draft = $state(blankFilter());
  let channelSearch = $state('');
  let companySearch = $state('');
  let body = $state(null);
  // Узел, по которому считается «нажали мимо»: кнопка и панель вместе. Своим
  // узлом, а не по именам классов — в двух списках подряд они одинаковы.
  let root = $state(null);

  const count = $derived(activeCount(draft));
  const channels = $derived(pickNames(options.channels, channelSearch));
  const companies = $derived(pickNames(options.companies, companySearch, COMPANY_MAX));

  // Одиночный выбор ряду вариантов приходит набором из одного: сам ряд про то,
  // один выбран или несколько, не знает.
  const alone = (value) => new Set([value]);

  function toggle() {
    if (!shown) {
      draft = { ...applied };
      channelSearch = '';
      companySearch = '';
    }
    onshown(!shown);
  }

  /** Выбрать срок активности и, если это «Периода…», довести панель к низу.
   *
   * Сроки — девятая группа из девяти, а панель ограничена по высоте: поля дат
   * появляются за нижней кромкой, и нажавший «Периода…» видит, что ничего не
   * произошло.
   */
  async function pickPreset(value) {
    draft.datePreset = value;
    if (value !== 'range') return;
    await tick();
    body.scrollTop = body.scrollHeight;
  }

  $effect(() => {
    // Нажатие мимо панели закрывает её и бросает черновик. Ухода мыши здесь
    // мало: панель большая, и мышь уходит с неё, пока человек ещё набирает.
    return whileOpen(shown, () => root, () => onshown(false));
  });
</script>

<!-- Панель падает из полосы, а не из-под кнопки: она вдвое шире полосы, и
     прижатая к кнопке у правого края она уходила бы за кромку списка.

     Обёртка вокруг них своей раскладки не имеет и стоит только затем, чтобы
     кнопка и панель считались одним местом: «мимо» сторож считает по узлу, а не
     по имени класса, и кнопка панели не принадлежит — она её сосед. -->
<div class="filter-wrap" bind:this={root}>
  <button
    class="icon-btn filter-btn"
    class:active={activeCount(applied) > 0}
    type="button"
    title="Фильтры"
    onclick={toggle}
  >
    <span class="material-symbols-outlined">filter_list</span>
  </button>

  {#if shown}
    <div class="pop filter-panel">
      <div class="bar filter-head">
        <span class="material-symbols-outlined">filter_list</span>
        <span class="filter-title">Фильтры</span>
        <span class="filter-meta">{count ? `${count} активных` : 'Без фильтров'}</span>
        <button class="modal-close filter-close" type="button" title="Закрыть" onclick={() => onshown(false)}>
          <span class="material-symbols-outlined">close</span>
        </button>
      </div>

      <div class="filter-body" bind:this={body}>
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
            hint="Поиск канала..."
            empty="Нет каналов"
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
            hint="Поиск компании..."
            empty="Нет совпадений"
            names={companies}
            chosen={draft.companies}
            search={companySearch}
            onsearch={(text) => (companySearch = text)}
            onpick={(name) => (draft.companies = toggled(draft.companies, name))}
          />
        </FilterGroup>

        <FilterGroup label="Score">
          <div class="filter-pair">
            <input
              class="input"
              type="number"
              placeholder="min"
              value={draft.scoreMin}
              oninput={(event) => (draft.scoreMin = event.currentTarget.value)}
            />
            <input
              class="input"
              type="number"
              placeholder="max"
              value={draft.scoreMax}
              oninput={(event) => (draft.scoreMax = event.currentTarget.value)}
            />
          </div>
        </FilterGroup>

        <FilterGroup label="Зарплата">
          <div class="filter-pair">
            <!-- Шаг в сотню: зарплату набирают тысячами, и стрелки поля с шагом
                 в единицу пришлось бы жать сотнями нажатий. -->
            <input
              class="input"
              type="number"
              min="0"
              step="100"
              placeholder="от"
              value={draft.salaryMin}
              oninput={(event) => (draft.salaryMin = event.currentTarget.value)}
            />
            <input
              class="input"
              type="number"
              min="0"
              step="100"
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

        <FilterGroup label="HR-контакт">
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
            onpick={pickPreset}
          />
          {#if draft.datePreset === 'range'}
            <div class="filter-pair filter-dates">
              <DatePicker value={draft.dateFrom} up onpick={(iso) => (draft.dateFrom = iso)} />
              <DatePicker value={draft.dateTo} up onpick={(iso) => (draft.dateTo = iso)} />
            </div>
          {/if}
        </FilterGroup>
      </div>

      <div class="modal-footer filter-foot">
        <!-- «Сбросить» — это «показать всё», а не «очистить поля»: список
             перечитывается сразу, панель закрывается. -->
        <button
          class="btn"
          type="button"
          onclick={() => {
            onshown(false);
            onapply(blankFilter());
          }}
        >
          <span class="material-symbols-outlined">restart_alt</span>
          Сбросить
        </button>
        <div class="filter-foot-right">
          <button class="btn" type="button" onclick={() => onshown(false)}>Отмена</button>
          <button
            class="btn primary"
            type="button"
            onclick={() => {
              onshown(false);
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
