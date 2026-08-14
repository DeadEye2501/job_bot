<script>
  // Строка канала: значок, имя, счёт вакансий и переключатель работы.
  import { channelName } from '$state/contacts.js';

  let { channel, ontoggle, onremove } = $props();

  const shown = $derived(channelName(channel));
</script>

<div class="contact-row" class:blocked={channel.is_blacklisted}>
  <!-- Строка не нажимается: карточки канала в окне пока нет, и нажатие,
       которое ничего не открывает, обещало бы её. Приедет карточка — приедет
       и нажатие. -->
  <div class="contact-main">
    {#if channel.avatar}
      <img class="avatar" src={channel.avatar} alt="" />
    {:else}
      <span class="avatar avatar-empty material-symbols-outlined">campaign</span>
    {/if}
    <span class="contact-names">
      <span class="contact-name">{shown.name}</span>
      {#if shown.handle}<span class="contact-handle">{shown.handle}</span>{/if}
    </span>
    <span class="contact-count">{channel.vacancy_count}</span>
  </div>

  <!-- Канал из отсева включить нельзя: обход всё равно его пропустит, и
       включённый переключатель обещал бы работу, которой не будет. -->
  <input
    type="checkbox"
    class="pipeline-toggle"
    checked={channel.is_active}
    disabled={channel.is_blacklisted}
    title={channel.is_blacklisted ? 'Канал в чёрном списке' : 'Опрашивать канал'}
    onchange={(event) => ontoggle(event.currentTarget.checked)}
  />

  <button class="icon-btn" type="button" title="Удалить канал" onclick={() => onremove()}>
    <span class="material-symbols-outlined">delete</span>
  </button>
</div>
