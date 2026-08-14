<script>
  // Строка вакансии: положение дел, оценка, название, подпись и стек.
  //
  // Не нажимается: карточка вакансии приедет своим слайсом, и нажатие сейчас
  // обещало бы то, чего за ним нет.
  import { scoreTone, shownStack, vacancyLine } from '$state/vacancies.js';

  let { vacancy, threshold } = $props();

  const shown = $derived(vacancyLine(vacancy, new Date()));
  const tone = $derived(scoreTone(vacancy.score, threshold));
  const stack = $derived(shownStack(vacancy.stack));
</script>

<div class="vac-row">
  <span class="vac-row-head">
    <span class="status-dot" data-status={vacancy.status}></span>
    {#if vacancy.score !== null}<span class="vac-score" data-tone={tone}>{vacancy.score}</span>{/if}
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
    {#each stack.chips as one (one.name)}
      <span class="mini-chip" class:matched={one.matched}>{one.name}</span>
    {/each}
    {#if stack.more}
      <span class="mini-chip more">+{stack.more}</span>
    {/if}
  </span>
</div>
