<script>
  // Резюме человека на сайте агрегатора: кружок «откликаться этим» и название,
  // уводящее на страницу резюме.
  //
  // Отметку решает база, а не список: кружок показывает пришедшее `chosen`, а
  // нажатие только сообщает, какое резюме выбрали. Само нажатие отменено —
  // иначе кружок стоял бы на нажатом и тогда, когда база выбор не приняла.
  let { resumes, site, onchoose, onopen } = $props();
</script>

<div class="card-section">
  {#if !resumes.length}
    <div class="mini-list-empty">Ваши резюме на {site} появятся здесь</div>
  {:else}
    {#each resumes as one (one.id)}
      <div class="resume-row">
        <input
          type="radio"
          name="resume-{site}"
          title="Откликаться этим резюме"
          checked={one.chosen}
          onclick={(event) => {
            event.preventDefault();
            onchoose(one.id);
          }}
        />
        <button class="resume-title link-hover" type="button" onclick={() => onopen(one.url)}>
          {one.title}
        </button>
      </div>
    {/each}
  {/if}
</div>
