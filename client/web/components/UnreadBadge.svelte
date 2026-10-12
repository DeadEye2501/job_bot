<script>
  // Счёт непрочитанного и список тех, от кого оно пришло.
  //
  // Список открывается над самим счётчиком: до переписки от него один нажим, а
  // не дорога через раздел контактов и поиск по имени.
  import { unreadLine } from '$state/people.js';

  let { count, open, loading, rows, ontoggle, onpick } = $props();
</script>

<button
  class="badge-unread"
  type="button"
  data-has-unread={count > 0}
  title={count > 0 ? 'Непрочитанные сообщения' : 'Новых сообщений нет'}
  aria-disabled={count === 0}
  onclick={() => ontoggle()}
>
  <span class="material-symbols-outlined">mail</span>
  <span class="count">{count}</span>
</button>

{#if open}
  <!-- Затемнения нет вовсе, но нажатие мимо список закрывает: он висит поверх
       окна, и оставленный открытым перекрывал бы правый край полосы. -->
  <div class="unread-popup-backdrop" role="presentation" onclick={() => ontoggle()}></div>

  <div class="pop-frame unread-popup" role="dialog" aria-label="Непрочитанные чаты">
    {#if loading && rows.length === 0}
      <div class="empty-note unread-popup-empty">Загрузка…</div>
    {:else if rows.length === 0}
      <div class="empty-note unread-popup-empty">Непрочитанных чатов нет.</div>
    {:else}
      <div class="unread-popup-list">
        {#each rows as row (row.hr_id)}
          {@const line = unreadLine(row)}
          <button class="unread-popup-row" type="button" onclick={() => onpick(row.hr_id)}>
            <div class="unread-popup-name">
              {line.name}
              {#if line.sub}
                <div class="unread-popup-sub">{line.sub}</div>
              {/if}
            </div>
            <div class="unread-popup-count">{row.unread_count}</div>
          </button>
        {/each}
      </div>
    {/if}
  </div>
{/if}
