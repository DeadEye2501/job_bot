<script>
  // Рама списка с поиском: шапка, счёт строк и то, что стоит вместо списка.
  //
  // Три списка контактов стоят в ней одинаково — каналы, компании, строки
  // отсева. Своё у каждого только кнопки в шапке, отбор над списком и сами
  // строки; всё это приходит разметкой снаружи.
  import { plural } from '$state/words.js';

  import SearchBox from './SearchBox.svelte';

  let {
    search,
    placeholder,
    onsearch,
    loaded,
    count,
    words,
    empty,
    nothing,
    filtered,
    actions = null,
    filters = null,
    children,
  } = $props();
</script>

<div class="list-head">
  <SearchBox value={search} {placeholder} {onsearch} />
  {#if actions}<div class="list-actions">{@render actions()}</div>{/if}
</div>

{#if filters}{@render filters()}{/if}

{#if !loaded}
  <div class="empty-note">Загрузка…</div>
{:else if !count}
  <!-- Пустых слов два, и разница несущая: «ничего не найдено» говорит, что
       список есть, а показать из него нечего, — и человек ищет причину в поле
       поиска, а не в том, что заводить он ещё ничего не начинал. -->
  <div class="empty-note">{filtered ? nothing : empty}</div>
{:else}
  <div class="list-count">{count} {plural(count, words[0], words[1], words[2])}</div>
  <div class="contact-list">{@render children()}</div>
{/if}
