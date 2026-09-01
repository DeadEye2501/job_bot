<script>
  // Строка канала: значок, имя с ником, отсев, счёт вакансий и переключатель.
  import { channelTitle, channelToggle } from '$state/channels.js';
  import { pressKey } from '$state/keys.js';

  import Avatar from './Avatar.svelte';
  import BlacklistMark from './BlacklistMark.svelte';
  import Handle from './Handle.svelte';
  import RowToggle from './RowToggle.svelte';

  let { channel, selected = false, onpick, ontoggle } = $props();

  const shown = $derived(channelToggle(channel));
  const title = $derived(channelTitle(channel));
</script>

<!-- Нажимается вся строка, а не имя в ней: нажатие на одном имени оставляет
     мёртвыми отступы строки, кружок и хвост. Кнопкой строка быть не может — в
     ней стоит переключатель опроса, — поэтому клавиатуре она отвечает
     разметкой.

     Клавишу строка принимает только свою: у переключателя внутри неё нажатие
     клавиши всплывает сюда, и без этого Enter на переключателе открывал бы
     карточку вместо переключения. -->
<div
  class="cnt-hr-row"
  class:selected
  class:blacklisted={shown.dim}
  role="button"
  tabindex="0"
  onclick={() => onpick()}
  onkeydown={(event) =>
    event.target === event.currentTarget && pressKey(event) && onpick()}
>
  <Avatar avatar={channel.avatar} icon="tag" />

  <span class="cnt-hr-info">
    <span class="cnt-hr-name" class:muted={!title.named}>
      {title.name}
    </span>
    <span class="cnt-hr-sub">
      <Handle username={channel.username} />
    </span>
  </span>

  <span class="cnt-hr-trailing">
    <BlacklistMark blocked={channel.is_blacklisted} />
    {#if channel.vacancy_count > 0}
      <span class="num-pill cnt-co-count">{channel.vacancy_count}</span>
    {/if}
    <!-- Канал из отсева включить нельзя: обход всё равно его пропустит, и
         включённый переключатель обещал бы работу, которой не будет. -->
    <RowToggle
      checked={shown.checked}
      disabled={shown.disabled}
      title={shown.title}
      {ontoggle}
    />
  </span>
</div>
