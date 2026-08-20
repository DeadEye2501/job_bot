<script>
  // Две панели вкладки контактов: список слева, карточка справа.
  //
  // Своим компонентом: так устроены три вкладки — люди, компании и каналы, — и
  // разметка у них была написана трижды. Машину страниц из них уже вынесли,
  // разметку нет, и она успела разойтись: у одной прокручивается список, у
  // другой панель целиком.
  //
  // Назван по разделу, а не «двумя панелями вообще»: та же раскладка есть у
  // вакансий, но под своей приставкой классов, и сводить их в одну разметку
  // нельзя — имена классов там несущие, по ним раздел и ищут поиском. Общее у
  // двух разделов вынесено оформлением, а не разметкой (`styles/master-detail.css`).
  //
  // Что внутри панелей, знает вкладка: полоса над списком, сами строки и
  // карточка приходят кусками разметки. Здесь только места, где они стоят, и
  // три состояния, одинаковые у всех троих: ещё читаем, читать нечего, никто не
  // выбран.
  //
  // Пустое место справа приходит строкой, а слева куском разметки: у списка
  // внутри него развилка по поиску («ничего не найдено» против «ещё никого не
  // заводили»), у панели выбирать не из чего.
  let {
    loaded,
    empty,
    chosen,
    detailEmpty,
    onlistscroll = null,
    ondetailscroll = null,
    toolbar,
    emptyNote,
    items,
    detail,
  } = $props();
</script>

<div class="cnt-layout">
  <section class="cnt-list-pane">
    <div class="bar cnt-list-toolbar">{@render toolbar()}</div>

    <div class="cnt-list" onscroll={onlistscroll}>
      {#if !loaded}
        <div class="cnt-list-empty">Загрузка…</div>
      {:else if empty}
        <div class="cnt-list-empty">{@render emptyNote()}</div>
      {:else}
        {@render items()}
      {/if}
    </div>
  </section>

  <section class="cnt-detail-pane" onscroll={ondetailscroll}>
    {#if !chosen}
      <div class="cnt-detail-empty">{detailEmpty}</div>
    {:else}
      {@render detail()}
    {/if}
  </section>
</div>
