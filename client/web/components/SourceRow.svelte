<script>
  // Строка источника вакансий — канала или агрегатора: значок, имя с подписью
  // под ним, отсев, счёт вакансий и переключатель обхода.
  //
  // Своим компонентом, потому что строки канала и агрегатора устроены одинаково
  // и разъезжались бы молча: нажатие всей строкой и своя клавиша — это то, что
  // в одной из копий легко забыть. Что показать, решает строка рода
  // (`ChannelRow`, `AggregatorRow`); подпись под именем приходит фрагментом —
  // у канала это ник своим видом, у агрегатора простой адрес.
  import { pressKey } from '$state/keys.js';

  import Avatar from './Avatar.svelte';
  import RowMarks from './RowMarks.svelte';
  import RowToggle from './RowToggle.svelte';

  let {
    avatar,
    icon,
    name,
    named = true,
    blocked,
    count,
    toggle,
    selected = false,
    onpick,
    ontoggle,
    sub,
  } = $props();
</script>

<!-- Нажимается вся строка, а не имя в ней: нажатие на одном имени оставляет
     мёртвыми отступы строки, кружок и хвост. Кнопкой строка быть не может — в
     ней стоит переключатель обхода, — поэтому клавиатуре она отвечает
     разметкой.

     Клавишу строка принимает только свою: у переключателя внутри неё нажатие
     клавиши всплывает сюда, и без этого Enter на переключателе открывал бы
     карточку вместо переключения. -->
<div
  class="cnt-hr-row"
  class:selected
  class:blacklisted={toggle.dim}
  role="button"
  tabindex="0"
  onclick={() => onpick()}
  onkeydown={(event) =>
    event.target === event.currentTarget && pressKey(event) && onpick()}
>
  <Avatar {avatar} {icon} />

  <span class="cnt-hr-info">
    <span class="cnt-hr-name" class:muted={!named}>{name}</span>
    <span class="cnt-hr-sub">{@render sub()}</span>
  </span>

  <span class="cnt-hr-trailing">
    <RowMarks {blocked} {count} />
    <RowToggle
      checked={toggle.checked}
      disabled={toggle.disabled}
      muted={toggle.muted}
      title={toggle.title}
      {ontoggle}
    />
  </span>
</div>
