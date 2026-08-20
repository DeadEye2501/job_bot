<script>
  // Поле, которое набирают руками, с панелью подходящих имён под ним.
  //
  // Не `<input list>` с `<datalist>`: панель у того рисует движок — своим
  // кеглем, своей рамкой и чёрным треугольником внутри поля, — и достать до неё
  // оформлением нельзя, отчего в тёмном окне она стоит чужой заплатой. Панель
  // здесь та же, что у `Dropdown`, и оформление у них общее.
  //
  // Набранное — состояние самого поля, а не того, кто его поставил: это буквы,
  // которые в нём стоят прямо сейчас, и наверху они никому не нужны. Наверх
  // уходит только выбранное имя.
  import { closeOnClickAway } from '$state/outside.js';
  import { matchingModels } from '$state/settings.js';

  let { value, options, placeholder, mono = false, maxlength = null, onsave } = $props();

  // `null` — в поле ещё не набирали, и отбор идёт по уже записанному имени: так
  // же ведёт себя системная подсказка, открытая на заполненном поле.
  let typed = $state(null);
  let open = $state(false);
  let root = $state(null);

  const shown = $derived(matchingModels(options, typed ?? value ?? ''));

  $effect(() => {
    if (!open) return;
    // Закрывается нажатием мимо: панель накрывает поля под собой, и уйти от неё
    // человек может куда угодно — хоть в соседнее поле, хоть в кнопку проверки.
    // «Мимо» считается по своему узлу: полей с подсказкой на экране настроек
    // два, и по классу они друг от друга не отличаются.
    return closeOnClickAway(() => root, () => (open = false));
  });

  function keep(name) {
    typed = null;
    open = false;
    onsave(name);
  }
</script>

<div class="cdd" bind:this={root}>
  <input
    class="input"
    class:mono
    autocomplete="off"
    {maxlength}
    {placeholder}
    {value}
    onfocus={() => (open = true)}
    oninput={(event) => (typed = event.currentTarget.value)}
    onblur={(event) => keep(event.currentTarget.value.trim())}
  />
  {#if open && shown.length}
    <div class="drop-panel cdd-panel" role="listbox" tabindex="-1">
      {#each shown as one (one)}
        <!-- Нажатие не уводит из поля: уйди оно — сработал бы уход, поле
             записало бы набранное, и выбранное имя уехало бы наверх вторым
             зовом поверх первого. -->
        <button
          class="cdd-option"
          class:active={one === value}
          type="button"
          onmousedown={(event) => event.preventDefault()}
          onclick={() => keep(one)}
        >
          {one}
        </button>
      {/each}
    </div>
  {/if}
</div>
