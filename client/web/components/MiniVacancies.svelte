<script>
  // Вакансии в чужой карточке: положение дел, оценка, название и давность.
  //
  // Один кусок на три карточки — канала, компании и человека. Так же на него
  // смотрит и мост: строку этих списков он собирает одним объявлением
  // (`_vacancy_mini_row_to_dict`), и разойдись они, на одном экране пропала бы
  // оценка, на другом — положение дел.
  //
  // Строка нажимается и уводит к самой вакансии: из карточки канала смотрят,
  // что он приносит, и тут же открывают принесённое.
  import { shortAgo } from '$state/vacancies.js';

  let { vacancies, empty, loading = false, onpick } = $props();
</script>

<div class="card-section">
  {#if !vacancies.length}
    <div class="mini-list-empty">{empty}</div>
  {:else}
    <div class="vacs-mini">
      {#each vacancies as one (one.id)}
        <div
          class="vac-mini-row"
          role="button"
          tabindex="0"
          onclick={() => onpick(one.id)}
          onkeydown={(event) => event.key === 'Enter' && onpick(one.id)}
        >
          <span class="status-dot" data-status={one.status}></span>
          {#if one.score !== null}<span class="num-pill vac-mini-score">{one.score}</span>{:else}<span></span>{/if}
          <span class="vac-mini-title">{one.title || '— без названия —'}</span>
          <span class="vac-mini-when">{shortAgo(one.created_at, new Date())}</span>
        </div>
      {/each}
    </div>
    {#if loading}
      <div class="mini-list-more">Загрузка…</div>
    {/if}
  {/if}
</div>
