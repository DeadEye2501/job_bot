<script>
  // Переключатель: в строке списка гасит отсев и включает опрос канала, в
  // окне заведения вакансии — «Отклик при создании».
  //
  // Положение держит своё, а не показывает довод напрямую. Нажатие меняет
  // галочку в самой странице сразу, и не сменись довод — а он не меняется,
  // когда мост отказал, — страница осталась бы с галочкой, которую никто не
  // ставил: человек считал бы отсев снятым, а он работал бы дальше.
  //
  // Отказ возвращает положение обратно; удача ничего не двигает — довод к тому
  // времени уже приехал таким же.
  import { untrack } from 'svelte';

  // `muted` — серый вид без запора: положение своё и нажимается, но работать по
  // нему сейчас ничего не будет (выключен общий выключатель над списком).
  //
  // `icon` — вид: без него пилюля строки списка, с ним — значок, который
  // светится включённым (`choice-line.css`). Галочка под значком та же самая,
  // и положение держится одинаково у обоих.
  let { checked, disabled = false, muted = false, title = null, icon = null, ontoggle } = $props();

  let on = $state(untrack(() => checked));

  // Довод сменили снаружи — идём за ним: список перечитывают и по вести от
  // бота, не только на своё нажатие.
  $effect(() => {
    on = checked;
  });

  async function flip(next) {
    on = next;
    if (!(await ontoggle(next))) on = checked;
  }
</script>

<!-- Нажатие дальше не идёт: строка вокруг переключателя бывает нажимаемой сама,
     и тогда переключение открывало бы её заодно с собой. -->
{#snippet box(look)}
  <input
    type="checkbox"
    class={look}
    class:locked={disabled}
    class:muted
    checked={on}
    {disabled}
    {title}
    onchange={(event) => flip(event.currentTarget.checked)}
    onclick={(event) => event.stopPropagation()}
  />
{/snippet}

{#if icon}
  <label class="icon-check" class:on class:locked={disabled} {title}>
    {@render box('icon-check-box')}
    <span class="material-symbols-outlined">{icon}</span>
  </label>
{:else}
  {@render box('toggle')}
{/if}
