<script>
  // Пороги отбора и ритм обхода: пять величин в одну строку.
  import { BOUNDS, SCORE_MAX, clampField, scorePercent } from '$state/settings.js';

  import SettingsSection from './SettingsSection.svelte';

  let { values, onsave } = $props();

  // Подписи — здесь, границы — в `state/settings.js` рядом с тем, кто по ним
  // зажимает: разъедься они, поле принимало бы одно, а показывало другое.
  const NUMBERS = [
    { key: 'poll_interval_sec', label: 'Интервал опроса', unit: 'сек', ...BOUNDS.poll_interval_sec },
    { key: 'backfill_limit', label: 'Сообщений за цикл', unit: 'шт', ...BOUNDS.backfill_limit },
    {
      key: 'dm_backfill_limit',
      label: 'DM-сообщений на HR',
      unit: 'шт',
      ...BOUNDS.dm_backfill_limit,
    },
  ];

  const LOCK_TITLE =
    'Когда включено, исходящие сообщения не уходят в Telegram — это режим проверки обхода без настоящей отправки';

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
      <div class="pipeline-label">Score threshold</div>
      <div class="slider-row">
        <input
          type="range"
          class="slider"
          min="0"
          max={SCORE_MAX}
          value={values.scoring_threshold}
          style="--pct: {scorePercent(values.scoring_threshold)}%;"
          onchange={(event) => onsave({ scoring_threshold: event.currentTarget.value })}
        />
        <span class="slider-num">{values.scoring_threshold}</span>
      </div>
    </div>

    {#each NUMBERS as one (one.key)}
      <div>
        <div class="pipeline-label">{one.label}</div>
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
    {/each}

    <div>
      <div class="pipeline-label" title={LOCK_TITLE}>Симуляция отправки</div>
      <div class="with-toggle">
        <input
          type="checkbox"
          class="toggle"
          checked={values.send_locked}
          onchange={(event) => onsave({ send_locked: event.currentTarget.checked })}
        />
      </div>
    </div>
  </div>
</SettingsSection>
