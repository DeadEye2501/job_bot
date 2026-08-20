<script>
  // Строка вакансии: положение дел, оценка, название, подпись и стек.
  import { scoreTone, shownStack, vacancyLine } from '$state/vacancies.js';

  let { vacancy, threshold, selected, onpick } = $props();

  const shown = $derived(vacancyLine(vacancy, new Date()));
  const tone = $derived(scoreTone(vacancy.score, threshold));
  const stack = $derived(shownStack(vacancy.stack));
</script>

<button class="vac-row" class:selected type="button" onclick={onpick}>
  <span class="vac-row-head">
    <span class="status-dot" data-status={vacancy.status}></span>
    {#if vacancy.score !== null}<span class="num-pill vac-score" data-tone={tone}>{vacancy.score}</span>{/if}
    <span class="vac-title">{shown.title}</span>
  </span>

  <!-- Половины подписи покрашены по-разному: компанию читают первой, а
       давность — последней, и одинаковый цвет заставлял бы разбирать строку
       целиком. -->
  <span class="vac-meta">
    <span class="v-co">{shown.company}</span><span class="sep">·</span>{shown.grade}<span
      class="sep">·</span>{shown.salary}<span class="sep">·</span><span class="when">{shown.when}</span>
  </span>

  <!-- Совпавшее с анкетой подсвечено: по нему и решают, стоит ли открывать. -->
  <span class="vac-stack">
    <!-- Ключ по месту, а не по названию: разбор кладёт в стек то, что нашёл, и
         одно и то же название приходит дважды. -->
    {#each stack.chips as one, at (at)}
      <span class="mini-chip" class:matched={one.matched}>{one.name}</span>
    {/each}
    {#if stack.more}
      <span class="mini-chip more">+{stack.more}</span>
    {/if}
  </span>
</button>
