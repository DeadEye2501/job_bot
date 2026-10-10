<script>
  // Две панели вкладки контактов: список слева, карточка справа.
  //
  // Своим компонентом: так устроены четыре вкладки — люди, компании, каналы и
  // агрегаторы, — и разметка у них была написана в каждой. Машину страниц из
  // них уже вынесли, разметку нет, и она успела разойтись: у одной
  // прокручивается список, у другой панель целиком.
  //
  // Назван по разделу, а не «двумя панелями вообще»: та же раскладка есть у
  // вакансий, но под своей приставкой классов, и сводить их в одну разметку
  // нельзя — имена классов там несущие, по ним раздел и ищут поиском. Общее у
  // двух разделов вынесено оформлением, а не разметкой (`styles/master-detail.css`).
  //
  // Полоса над списком у всех одна — поиск и кнопка заведения; своё у вкладки
  // в ней только то, что встаёт после них (`tools`). Строки и карточка приходят
  // кусками разметки. Здесь места, где они стоят, и три состояния, одинаковые у
  // всех: ещё читаем, читать нечего, никто не выбран.
  //
  // Читать нечего — двумя словами, и разница несущая: «ничего не найдено»
  // говорит, что виноват запрос, а `none` — что записей ещё не заводили.
  import AddButton from './AddButton.svelte';
  import SearchBox from './SearchBox.svelte';

  let {
    loaded,
    empty,
    chosen,
    search,
    searchHint,
    addTitle,
    addIcon,
    none,
    detailEmpty,
    onsearch,
    onadd,
    onlistscroll = null,
    ondetailscroll = null,
    tools = null,
    items,
    detail,
  } = $props();
</script>

<div class="cnt-layout">
  <section class="cnt-list-pane">
    <div class="bar cnt-list-toolbar">
      <SearchBox value={search} placeholder={searchHint} {onsearch} />
      <AddButton title={addTitle} icon={addIcon} onclick={onadd} />
      {@render tools?.()}
    </div>

    <div class="cnt-list" onscroll={onlistscroll}>
      {#if !loaded}
        <div class="empty-note cnt-list-empty">Загрузка…</div>
      {:else if empty}
        <div class="empty-note cnt-list-empty">
          {search ? `Ничего не найдено по запросу «${search}»` : none}
        </div>
      {:else}
        {@render items()}
      {/if}
    </div>
  </section>

  <section class="cnt-detail-pane" onscroll={ondetailscroll}>
    {#if !chosen}
      <div class="empty-note cnt-detail-empty">{detailEmpty}</div>
    {:else}
      {@render detail()}
    {/if}
  </section>
</div>
