<script>
  // Поле, которое набирают руками, с панелью подходящих имён под ним.
  //
  // Не `<input list>` с `<datalist>`: панель у того рисует движок — своим
  // кеглем, своей рамкой и чёрным треугольником внутри поля, — и достать до неё
  // оформлением нельзя, отчего в тёмном окне она стоит чужой заплатой. Панель
  // здесь та же, что у `Dropdown`, и оформление у них общее.
  //
  // `asked` — чем набранное принимается наверх, и это единственное, чем
  // расходятся два места, где поле стоит. Ложь: принимает уход из поля — так
  // правят имя модели в настройках, где принятое ничего не заводит. Истина:
  // принимают Enter и галочка в конце строки — так называют чужую карточку в
  // форме вакансии, где принятое имя **заводит запись**, и уход мышью мимо
  // поля завёл бы карточку, которой человек не просил.
  //
  // Набранное — состояние самого поля, а не того, кто его поставил: это буквы,
  // которые в нём стоят прямо сейчас, и наверху они никому не нужны. Наверх
  // уходит только принятое имя.
  import { matching } from '$state/search.js';
  import { whileOpen } from '$state/outside.js';

  import DropPanel from './DropPanel.svelte';

  let {
    value,
    options,
    placeholder,
    asked = false,
    mono = false,
    maxlength = null,
    onsave,
  } = $props();

  // `null` — в поле ещё не набирали, и отбор идёт по уже записанному имени: так
  // же ведёт себя системная подсказка, открытая на заполненном поле.
  let typed = $state(null);
  let open = $state(false);
  let root = $state(null);

  // То, что стоит в поле прямо сейчас: по нему и просеивается подсказка, и по
  // нему же она помечает выбранное. Пометка говорит «вот это в поле», и
  // оставшись на принятом раньше имени, она врала бы про стёртое поле.
  const inField = $derived(typed ?? value ?? '');

  const shown = $derived(matching(options, inField));

  // Есть ли что принимать: набрано непустое и не то же, что принято раньше.
  // Пустое поле в счёт не идёт: галочка над ним обещала бы завести карточку
  // без имени, а такую не найти потом ничем. Снять уже принятое она при этом не
  // мешает — стёртое поле принимают Enter'ом.
  const pending = $derived(
    typed !== null && typed.trim() !== '' && typed.trim() !== value,
  );

  $effect(() => {
    // Закрывается нажатием мимо: панель накрывает поля под собой, и уйти от неё
    // человек может куда угодно — хоть в соседнее поле, хоть в кнопку проверки.
    // «Мимо» считается по своему узлу: полей с подсказкой на экране настроек
    // два, и по классу они друг от друга не отличаются.
    return whileOpen(open, () => root, () => (open = false));
  });

  /** Принять имя: наверх уходит оно, поле возвращается к показу принятого. */
  function keep(name) {
    typed = null;
    open = false;
    onsave(name);
  }
</script>

<div class="cdd" bind:this={root}>
  <div class="confirm-field">
    <input
      class="input"
      class:mono
      autocomplete="off"
      {maxlength}
      {placeholder}
      value={inField}
      onfocus={() => (open = true)}
      oninput={(event) => (typed = event.currentTarget.value)}
      onblur={asked ? undefined : (event) => keep(event.currentTarget.value.trim())}
      onkeydown={(event) => {
        if (!asked || event.key !== 'Enter') return;
        event.preventDefault();
        keep(event.currentTarget.value.trim());
      }}
    />
    {#if asked && pending}
      <button
        class="icon-btn"
        type="button"
        title="Принять имя"
        onclick={() => keep(typed.trim())}
      >
        <span class="material-symbols-outlined">check</span>
      </button>
    {/if}
  </div>
  {#if open && shown.length}
    <DropPanel options={shown} value={inField} keepFocus onpick={keep} />
  {/if}
</div>
