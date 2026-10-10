<script>
  // Люди компании в её карточке: кружок, имя и подпись под ним.
  //
  // Строка нажимается и уводит к самому человеку: из карточки компании смотрят,
  // кто из неё писал, и тут же открывают того, кому отвечать.
  import Avatar from './Avatar.svelte';
  import MiniList from './MiniList.svelte';
  import { personName } from '$state/people.js';
  import { atHandle } from '$state/telegram.js';
  import { vacancyCount } from '$state/words.js';

  let { people, empty, onpick } = $props();
</script>

<MiniList items={people} {empty} listClass="hrs-mini" rowClass="hr-mini-row" {onpick}>
  {#snippet row(one)}
    <Avatar avatar={one.avatar} name={one.name} icon="person" />
    <div>
      <div class="hr-mini-name">{personName(one)}</div>
      <span class="hr-mini-meta">
        {#if one.telegram_username}{atHandle(one.telegram_username)} · {/if}
        {vacancyCount(one.vacancy_count)}
      </span>
    </div>
    <span class="material-symbols-outlined hr-mini-go">arrow_forward</span>
  {/snippet}
</MiniList>
