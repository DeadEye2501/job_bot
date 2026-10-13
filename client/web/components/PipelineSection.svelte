<script>
  // Пороги отбора и ритм обхода: шесть величин в две строки по три — сверху
  // порог, интервал и режим автоотклика, снизу три лимита.
  import { untrack } from 'svelte';

  import { BOUNDS, SCORE_MAX, clampField, scorePercent, thresholdState } from '$state/settings.js';

  import SettingsSection from './SettingsSection.svelte';

  let { values, onsave } = $props();

  // Подписи — здесь, границы — в `state/settings.js` рядом с тем, кто по ним
  // зажимает: разъедься они, поле принимало бы одно, а показывало другое.
  const INTERVAL = {
    key: 'poll_interval_sec',
    label: 'Интервал опроса',
    unit: 'сек',
    ...BOUNDS.poll_interval_sec,
  };
  // Слева направо — от «не откликаться вовсе» к «откликаться самому».
  const AUTO_APPLY = [
    { value: 'false', label: 'Только поиск' },
    { value: 'confirm', label: 'Отклик с подтверждением' },
    { value: 'true', label: 'Автоотклик' },
  ];
  const LIMITS = [
    { key: 'backfill_limit', label: 'Сообщений за цикл', unit: 'шт', ...BOUNDS.backfill_limit },
    {
      key: 'aggregator_backfill_limit',
      label: 'Вакансий с агрегатора',
      unit: 'шт',
      ...BOUNDS.aggregator_backfill_limit,
    },
    {
      key: 'dm_backfill_limit',
      label: 'DM-сообщений на HR',
      unit: 'шт',
      ...BOUNDS.dm_backfill_limit,
    },
  ];

  // Порог живёт своим состоянием: запись уходит по отпусканию, и до ответа
  // моста число рядом с ползунком отставало бы — порог тянули бы вслепую.
  let threshold = $state(untrack(() => thresholdState({ saved: values.scoring_threshold })));

  // Приехавшее сверху перебивает набранное: перечитанные настройки значат, что
  // порог сменили не здесь. Сверяем именно число, а не сам приход настроек:
  // запись соседнего поля отдаёт новый объект целиком, и без сверки она сбивала
  // бы порог, который в этот миг тянут.
  $effect(() => {
    const saved = values.scoring_threshold;
    if (saved !== untrack(() => threshold.saved)) threshold = thresholdState({ saved });
  });

  function settle() {
    threshold = threshold.commit();
    onsave({ scoring_threshold: threshold.saved });
  }

  /** Принять число из поля и показать в нём то, что уехало на мост.
   *
   * Поле переписывается вручную: набранное «0» превращается в «10», а «абв» —
   * в прежнее значение, но сам ввод остался бы стоять на экране. Человек читал
   * бы своё, а бот работал бы по другому.
   */
  function keep(field, one) {
    const value = clampField(field.value, {
      min: one.min,
      max: one.max,
      fallback: values[one.key],
    });
    field.value = String(value);
    onsave({ [one.key]: value });
  }
</script>

<SettingsSection icon="tune" title="Пайплайн">
  <div class="pipeline-row">
    <div>
      <div class="field-caption pipeline-label">Score threshold</div>
      <div class="slider-row">
        <input
          type="range"
          class="slider"
          min="0"
          max={SCORE_MAX}
          value={threshold.shown}
          style="--pct: {scorePercent(threshold.shown)}%;"
          oninput={(event) => (threshold = threshold.drag(Number(event.currentTarget.value)))}
          onchange={settle}
        />
        <span class="slider-num">{threshold.shown}</span>
      </div>
    </div>

    {@render number(INTERVAL)}

    <div>
      <div class="field-caption pipeline-label mode-caption">
        {#each AUTO_APPLY as one (one.value)}
          <span aria-hidden={one.value !== values.auto_apply}>{one.label}</span>
        {/each}
      </div>
      <div class="mode-radios">
        {#each AUTO_APPLY as one (one.value)}
          <input
            type="radio"
            name="auto_apply"
            value={one.value}
            title={one.label}
            checked={one.value === values.auto_apply}
            onchange={() => onsave({ auto_apply: one.value })}
          />
        {/each}
      </div>
    </div>

    {#each LIMITS as one (one.key)}
      {@render number(one)}
    {/each}
  </div>
</SettingsSection>

{#snippet number(one)}
  <div>
    <div class="field-caption pipeline-label">{one.label}</div>
    <div class="with-unit">
      <input
        class="input"
        type="number"
        min={one.min}
        max={one.max}
        value={values[one.key]}
        onblur={(event) => keep(event.currentTarget, one)}
      />
      <span class="unit">{one.unit}</span>
    </div>
  </div>
{/snippet}
