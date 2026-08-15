<script>
  // Люди компании в её карточке: кружок, имя и подпись под ним.
  //
  // Строка нажимается и уводит к самому человеку: из карточки компании смотрят,
  // кто из неё писал, и тут же открывают того, кому отвечать.
  import Avatar from './Avatar.svelte';
  import { personName } from '$state/contacts.js';
  import { plural } from '$state/words.js';

  let { people, empty, onpick } = $props();
</script>

<div class="cnt-det-section">
  {#if !people.length}
    <div class="cnt-vacs-empty">{empty}</div>
  {:else}
    <div class="hrs-mini">
      {#each people as one (one.id)}
        <div
          class="hr-mini-row"
          role="button"
          tabindex="0"
          onclick={() => onpick(one.id)}
          onkeydown={(event) => event.key === 'Enter' && onpick(one.id)}
        >
          <Avatar avatar={one.avatar} name={one.name} icon="person" />
          <div>
            <div class="hr-mini-name">{personName(one)}</div>
            <span class="hr-mini-meta">
              {#if one.telegram_username}@{one.telegram_username} · {/if}
              {one.vacancy_count} {plural(one.vacancy_count, 'вакансия', 'вакансии', 'вакансий')}
            </span>
          </div>
          <span class="material-symbols-outlined hr-mini-go">arrow_forward</span>
        </div>
      {/each}
    </div>
  {/if}
</div>
