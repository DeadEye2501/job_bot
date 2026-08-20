<script>
  // Ник в шапке карточки: нажимаемый, если он есть.
  //
  // Своим компонентом: так подписаны шапки человека и канала, и написано это
  // было дважды, тринадцать строк в строку. Прочерк вместо ника тут свой, не
  // списочный: под шапкой стоит вторая строка, и слова в ней читаются рядом.
  import { telegramHref } from '$state/telegram.js';

  let { username, onopen } = $props();
</script>

{#if username}
  <button
    class="cnt-det-link"
    type="button"
    title="Открыть в Telegram"
    onclick={() => onopen(telegramHref(username))}
  >
    @{username}
  </button>
{:else}
  <span>@—</span>
{/if}
