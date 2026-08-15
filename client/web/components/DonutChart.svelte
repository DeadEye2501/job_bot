<script>
  // Кольцо долей: сегменты по кругу и общее число в середине.
  //
  // Рисуется обводкой одного круга, а не дугами: у обводки длина считается
  // одной формулой, и стык сегментов не расходится на доли точки.
  let { parts, total, label } = $props();

  const RADIUS = 42;
  const LENGTH = 2 * Math.PI * RADIUS;

  const drawn = $derived(
    parts.reduce(
      (going, one) => {
        const length = (one.percent / 100) * LENGTH;
        going.items.push({ ...one, length, offset: -going.used });
        going.used += length;
        return going;
      },
      { items: [], used: 0 },
    ).items,
  );
</script>

<div class="donut-wrap">
  <svg class="donut" viewBox="0 0 100 100">
    {#each drawn as one (one.name)}
      <circle
        class="donut-part"
        data-status={one.name}
        cx="50"
        cy="50"
        r={RADIUS}
        stroke-dasharray="{one.length} {LENGTH - one.length}"
        stroke-dashoffset={one.offset}
      />
    {/each}
  </svg>
  <div class="donut-center">
    <div class="big-num donut-total">{total}</div>
    <div class="donut-label">{label}</div>
  </div>
</div>
