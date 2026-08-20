<script>
  // Рама окна: затемнение, коробка поверх него и клавиатура.
  //
  // Своим компонентом: окон шесть, и начинались они одинаково — то же
  // затемнение, та же коробка, тот же Escape. Нажатие по затемнению закрывало
  // окно у четверых из шести, а у двоих нет: поправка до копий не доехала.
  //
  // `extra` — имя своего вида коробки: ширина у окон разная, и задаёт её каждое
  // само. `confirm` просит только подтверждение необратимого: там Enter значит
  // «да», а в окнах с заметкой в несколько строк он обрывал бы набор.
  import ModalKeys from './ModalKeys.svelte';

  let { extra = '', confirm = null, onclose, children } = $props();
</script>

<ModalKeys close={onclose} {confirm} />

<!-- Нажатие по затемнению закрывает окно, нажатие внутри коробки — нет:
     сверяем, что нажали ровно в затемнение, а не всплыло из содержимого. -->
<div
  class="modal-backdrop"
  role="presentation"
  onclick={(event) => event.target === event.currentTarget && onclose()}
>
  <div class="modal-dialog {extra}" role="dialog" aria-modal="true">
    {@render children()}
  </div>
</div>
