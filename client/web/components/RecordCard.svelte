<script>
  // Запись анкеты — место работы или проект: свёрнутая шапка и тело под ней.
  import { pressKey } from '$state/keys.js';

  let { title, open, ontoggle, onremove, removeLabel, children } = $props();
</script>

<div class="exp-card" class:collapsed={!open}>
  <!-- Нажимается вся шапка, а не одна стрелка: свёрнутых карточек столбик, и
       целиться в значок ради раскрытия человеку не за что. -->
  <div
    class="exp-header"
    role="button"
    tabindex="0"
    onclick={() => ontoggle()}
    onkeydown={(event) => pressKey(event) && ontoggle()}
  >
    <span class="material-symbols-outlined collapse-arrow">expand_more</span>
    <div class="exp-summary">
      <strong>{title.name}</strong>
      {#if title.role}· <span class="role">{title.role}</span>{/if}
      {#if title.period}<span class="period">{title.period}</span>{/if}
    </div>
    <button
      class="exp-delete trash"
      type="button"
      title={removeLabel}
      onclick={(event) => {
        event.stopPropagation();
        onremove();
      }}
    >
      <span class="material-symbols-outlined">delete</span>
    </button>
  </div>

  {#if open}
    <div class="exp-body">
      {@render children()}
    </div>
  {/if}
</div>
