<script>
  // Вакансии в чужой карточке: название, положение дел и оценка.
  //
  // Один кусок на три карточки — канала, компании и человека. Так же на него
  // смотрит и мост: строку этих списков он собирает одним объявлением
  // (`_vacancy_mini_row_to_dict`), и разойдись они, на одном экране пропала бы
  // оценка, на другом — положение дел.
  //
  // Страницами дочитывается только список канала: там вакансий бывают тысячи.
  let { vacancies, empty, hasMore = false, onmore = null } = $props();
</script>

<div class="card-vacancies">
  {#if !vacancies.length}
    <div class="empty-note">{empty}</div>
  {:else}
    {#each vacancies as one (one.id)}
      <div class="stat-line">
        <span class="stat-name">{one.title || 'Без названия'}</span>
        <span class="stat-value">
          <span class="status-dot" data-status={one.status}></span>
          {one.score ?? '—'}
        </span>
      </div>
    {/each}
    {#if hasMore}
      <button class="add-more" type="button" onclick={() => onmore()}>Показать ещё</button>
    {/if}
  {/if}
</div>
