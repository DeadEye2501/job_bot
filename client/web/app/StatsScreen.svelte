<script>
  // Экран статистики: пять карточек за выбранный срок.
  //
  // Каждая карточка спрашивает своё: считаются они по-разному, и ждать самую
  // медленную ради самой быстрой незачем. Ответ, пришедший на прежний срок,
  // отбрасывается — иначе карточки показывали бы разные периоды разом.
  //
  // Зовы написаны литералами, а не собраны таблицей путей: имя, спрятанное в
  // таблицу, выпадает из шва с мостом — сторож ищет его на месте зова.

  import StatsCard from '$components/StatsCard.svelte';
  import StatsChannelsCard from '$components/StatsChannelsCard.svelte';
  import StatsKpiRow from '$components/StatsKpiRow.svelte';
  import StatsResponsesCard from '$components/StatsResponsesCard.svelte';
  import StatsSkillsCard from '$components/StatsSkillsCard.svelte';
  import StatsStatusCard from '$components/StatsStatusCard.svelte';
  import { living } from '$state/alive.js';
  import { PERIODS, sliceTarget, sourceRows } from '$state/stats.js';

  let { ask, onslice, onsource } = $props();

  let period = $state('month');
  let kpi = $state(null);
  let breakdown = $state(null);
  let responses = $state(null);
  let skills = $state(null);
  let channels = $state(null);

  const alive = living();

  const loading = $derived(!kpi || !breakdown || !responses || !skills || !channels);

  /** Спросить карточку и принять ответ, если он ещё нужен.
   *
   * Срок мог смениться, пока ответ шёл: чужие числа под новой подписью
   * читались бы как настоящие.
   */
  async function taken(asked, answer) {
    return answer !== null && alive.now && asked === period ? answer : null;
  }

  async function load() {
    const asked = period;
    kpi = breakdown = responses = skills = channels = null;
    ask('stats.kpi', asked).then(async (one) => (kpi = (await taken(asked, one)) ?? kpi));
    ask('stats.status_breakdown', asked).then(
      async (one) => (breakdown = (await taken(asked, one)) ?? breakdown),
    );
    ask('stats.hr_responses', asked).then(
      async (one) => (responses = (await taken(asked, one)) ?? responses),
    );
    ask('stats.skills', asked).then(async (one) => (skills = (await taken(asked, one)) ?? skills));
    ask('stats.channels_pipeline', asked).then(
      async (one) => (channels = (await taken(asked, one)) ?? channels),
    );
  }

  $effect(() => {
    const settled = alive.mounted();
    // Читает `period` нарочно: сменился срок — эффект заводится заново и
    // перечитывает всё сам. Второй зов из обработчика вкладки удвоил бы
    // работу моста на каждое нажатие.
    period;
    load();
    return () => {
      settled();
    };
  });
</script>

<div class="screen-body">
  <div class="stats-toolbar">
    {#each PERIODS as one (one.key)}
      <button
        class="pill stats-period-pill"
        class:active={period === one.key}
        type="button"
        onclick={() => (period = one.key)}
      >
        {one.label}
      </button>
    {/each}

    <!-- Числа считает бот, а не окно: пересчитать за тот же срок иначе
         нечем — пришлось бы уходить в другой раздел и возвращаться. -->
    <button
      class="stats-refresh-btn"
      class:spinning={loading}
      type="button"
      title="Обновить"
      onclick={load}
    >
      <span class="material-symbols-outlined">sync</span>
    </button>
  </div>

  <div class="stats-grid">
    <StatsKpiRow answer={kpi} {period} />

    <StatsCard title="Статусы" ready={!!breakdown} span="6">
      <StatsStatusCard counts={breakdown.counts} onpick={(name) => onslice(sliceTarget(name, period, new Date()))} />
    </StatsCard>

    <StatsCard title="Ответы HR" ready={!!responses} span="6">
      <StatsResponsesCard answer={responses} />
    </StatsCard>

    <StatsCard title="Скилы" ready={!!skills} span="12">
      {#if skills.skills.length}
        <StatsSkillsCard skills={skills.skills} />
      {:else}
        <div class="stats-loading">Нет скилов с count ≥ {skills.min_count} за период</div>
      {/if}
    </StatsCard>

    <StatsCard title="Источники" ready={!!channels} span="12">
      {#if channels.channels.length}
        <StatsChannelsCard channels={sourceRows(channels.channels)} onpick={onsource} />
      {:else}
        <div class="stats-loading">Нет вакансий из источников за период</div>
      {/if}
    </StatsCard>
  </div>
</div>
