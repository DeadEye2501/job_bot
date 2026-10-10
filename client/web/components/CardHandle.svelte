<script>
  // Ник в шапке карточки: нажимаемый, если он есть.
  //
  // Своим компонентом: так подписаны шапки человека и канала. Прочерк вместо
  // ника тут свой, не списочный: под шапкой стоит вторая строка, и слова в ней
  // читаются рядом.
  import { atHandle, telegramHref } from '$state/telegram.js';

  let { username, onopen } = $props();
</script>

{#if username}
  <button
    class="cnt-det-link link-hover"
    type="button"
    title="Открыть в Telegram"
    onclick={() => onopen(telegramHref(username))}
  >
    {atHandle(username)}
  </button>
{:else}
  <span>@—</span>
{/if}
