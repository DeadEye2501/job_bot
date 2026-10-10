<script>
  // Строка списка контактов — человека, компании, канала или агрегатора:
  // значок, имя с подписью под ним, отсев и хвост из чисел и переключателя.
  //
  // Своим компонентом, потому что строки всех четырёх вкладок устроены
  // одинаково и разъезжались бы молча: нажатие всей строкой и своя клавиша —
  // это то, что в одной из копий легко забыть. Что показать, решает строка рода
  // (`PersonRow`, `CompanyRow`, `ChannelRow`, `AggregatorRow`); подпись под
  // именем приходит фрагментом — у каждого рода она своего вида.
  //
  // Хвост у родов разный: у человека непрочитанное, у компании и источников
  // счёт вакансий, переключатель обхода — только у источников.
  import { pressKey } from '$state/keys.js';

  import Avatar from './Avatar.svelte';
  import RowMarks from './RowMarks.svelte';
  import RowToggle from './RowToggle.svelte';

  let {
    avatar,
    initialsOf,
    icon,
    name,
    named = true,
    blocked,
    dim,
    count,
    unread,
    toggle,
    selected = false,
    onpick,
    ontoggle,
    sub,
  } = $props();
</script>

<!-- Нажимается вся строка, а не имя в ней: нажатие на одном имени оставляет
     мёртвыми отступы строки, кружок и хвост. Кнопкой строка быть не может — в
     строке источника стоит переключатель обхода, — поэтому клавиатуре она
     отвечает разметкой.

     Клавишу строка принимает только свою: у переключателя внутри неё нажатие
     клавиши всплывает сюда, и без этого Enter на переключателе открывал бы
     карточку вместо переключения. -->
<div
  class="cnt-hr-row"
  class:selected
  class:blacklisted={dim}
  role="button"
  tabindex="0"
  onclick={() => onpick()}
  onkeydown={(event) =>
    event.target === event.currentTarget && pressKey(event) && onpick()}
>
  <Avatar {avatar} name={initialsOf} {icon} />

  <span class="cnt-hr-info">
    <span class="cnt-hr-name" class:muted={!named}>{name}</span>
    <span class="cnt-hr-sub">{@render sub()}</span>
  </span>

  <span class="cnt-hr-trailing">
    <RowMarks {blocked} {count} />
    {#if unread}
      <span class="cnt-hr-unread">{unread}</span>
    {/if}
    {#if toggle}
      <RowToggle
        checked={toggle.checked}
        disabled={toggle.disabled}
        muted={toggle.muted}
        title={toggle.title}
        {ontoggle}
      />
    {/if}
  </span>
</div>
